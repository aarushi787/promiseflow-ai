from datetime import datetime
from uuid import uuid4
import pytest
from backend.engine import CpSatProvider
from backend.validation import validate_plan
from test_api import client, login


@pytest.fixture(autouse=True)
def execution_clock(monkeypatch):
    monkeypatch.setattr(
        "backend.execution.local_now", lambda f: datetime(2026, 9, 7, 10, 15)
    )


def payload(
    client, operation="A/B1/10", kind="START", at="2026-09-07T08:00", quantity=0
):
    d = client.get("/api/execution").json()
    return dict(
        request_id=str(uuid4()),
        revision=d["revision"],
        version_id=d["version_id"],
        operation_id=operation,
        kind=kind,
        occurred_at=at,
        quantity_completed=quantity,
        reason="Observed on the shop floor",
    )


def event(client, **kwargs):
    r = client.post("/api/execution/events", json=payload(client, **kwargs))
    assert r.status_code == 200, r.text
    return r


def finish_order(client):
    event(client)
    event(client, kind="COMPLETE", quantity=100, at="2026-09-07T09:00")
    event(client, operation="A/B1/20", at="2026-09-07T09:00")
    event(
        client,
        operation="A/B1/20",
        kind="COMPLETE",
        quantity=100,
        at="2026-09-07T10:00",
    )


def reconciliation(client):
    return dict(
        revision=client.get("/api/execution").json()["revision"],
        reason="Physical balance verified after production",
        balances=[
            dict(material_id="MAT", stock=900, reserved=0, incoming=0, arrival=None)
        ],
    )


def test_actuals_invalidate_proposals_and_preserve_approved_plan(client):
    login(client)
    before = client.get("/api/factory").json()
    proposal = client.post("/api/plan").json()
    event(client)
    after = client.get("/api/factory").json()
    assert after["plan"] == before["plan"]
    assert after["factory"] == before["factory"]
    assert after["revision"] == before["revision"] + 1
    assert after["execution_pending_orders"] == ["A"]
    assert client.post(f'/api/versions/{proposal["id"]}/activate').status_code == 409
    assert client.post("/api/plan").status_code == 409
    assert (
        client.get("/api/readiness").json()["status"]
        == "Blocked by unreconciled actuals"
    )
    assert (
        client.put(
            "/api/factory",
            json={"factory": after["factory"], "revision": after["revision"]},
        ).status_code
        == 409
    )


def test_events_are_idempotent_and_revision_checked(client):
    login(client)
    body = payload(client)
    assert client.post("/api/execution/events", json=body).status_code == 200
    assert client.post("/api/execution/events", json=body).json()["replayed"]
    assert len(client.get("/api/execution").json()["events"]) == 1
    assert (
        client.post(
            "/api/execution/events", json={**body, "reason": "Different request"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/execution/events", json={**body, "request_id": str(uuid4())}
        ).status_code
        == 409
    )


def test_roles_and_hold_release(client):
    login(client, "sales")
    assert client.post("/api/execution/events", json=payload(client)).status_code == 403
    login(client, "supervisor")
    event(client)
    event(client, kind="HOLD", at="2026-09-07T08:10")
    assert (
        client.post(
            "/api/execution/events",
            json=payload(client, kind="RESUME", at="2026-09-07T08:15"),
        ).status_code
        == 409
    )
    assert (
        client.post("/api/execution/reconcile", json=reconciliation(client)).status_code
        == 403
    )
    login(client)
    event(client, kind="RESUME", at="2026-09-07T08:15")


def test_quantity_transition_and_partial_work_gate(client):
    login(client)
    event(client)
    event(client, kind="PROGRESS", quantity=40, at="2026-09-07T08:20")
    for quantity in (20, 40, 101):
        assert (
            client.post(
                "/api/execution/events",
                json=payload(
                    client, kind="PROGRESS", quantity=quantity, at="2026-09-07T08:30"
                ),
            ).status_code
            == 422
        )
    assert (
        client.post(
            "/api/execution/events",
            json=payload(client, kind="COMPLETE", quantity=40, at="2026-09-07T08:30"),
        ).status_code
        == 422
    )
    event(client, kind="PAUSE", quantity=40, at="2026-09-07T08:30")
    assert (
        client.post(
            "/api/execution/events",
            json=payload(client, kind="COMPLETE", quantity=100, at="2026-09-07T08:40"),
        ).status_code
        == 422
    )
    event(client, kind="RESUME", quantity=40, at="2026-09-07T08:40")
    d = client.get("/api/execution").json()
    row = next(o for o in d["operations"] if o["id"] == "A/B1/10")
    assert row["remaining_quantity"] == 60
    assert not d["can_reconcile"]
    assert (
        client.post("/api/execution/reconcile", json=reconciliation(client)).status_code
        == 409
    )


def test_precedence_and_shared_capacity(client):
    login(client)
    assert (
        client.post(
            "/api/execution/events", json=payload(client, operation="A/B1/20")
        ).status_code
        == 422
    )
    event(client)
    # Either machine can be eligible, but the same fixture/operator cannot overlap.
    r = client.post(
        "/api/execution/events",
        json=payload(client, operation="B/B1/10", at="2026-09-07T08:10"),
    )
    assert r.status_code == 422
    assert "occupied" in r.text


def test_time_and_identity_validation(client):
    login(client)
    for changes in (
        {"operation_id": "MISSING"},
        {"occurred_at": "2026-09-08T08:00"},
        {"occurred_at": "2026-09-07T08:00:01"},
        {"occurred_at": "2026-09-07T08:00+05:30"},
    ):
        assert (
            client.post(
                "/api/execution/events", json={**payload(client), **changes}
            ).status_code
            == 422
        )
    event(client)
    assert (
        client.post(
            "/api/execution/events", json=payload(client, kind="COMPLETE", quantity=100)
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/execution/events",
            json=payload(client, kind="PAUSE", at="2026-09-07T07:59"),
        ).status_code
        == 422
    )


def test_whole_order_reconciliation_then_replan(client):
    login(client)
    before = client.get("/api/factory").json()
    finish_order(client)
    assert client.get("/api/execution").json()["can_reconcile"]
    r = client.post("/api/execution/reconcile", json=reconciliation(client))
    assert r.status_code == 200, r.text
    after = client.get("/api/factory").json()
    assert after["active_version"] == before["active_version"]
    assert not after["execution_pending_orders"]
    assert (
        next(o for o in after["factory"]["orders"] if o["id"] == "A")["status"]
        == "COMPLETED"
    )
    assert after["factory"]["materials"][0]["stock"] == 900  # No second deduction.
    proposed = client.post("/api/plan")
    assert proposed.status_code == 200, proposed.text
    p = proposed.json()
    assert {o["order_id"] for o in p["result"]["operations"]} == {"B"}
    assert all(o["start"] >= "2026-09-07T10:15" for o in p["result"]["operations"])
    impact = next(
        i for i in p["result"]["comparison"]["impacts"] if i["order_id"] == "A"
    )
    assert impact["after_status"] == "COMPLETED" and not impact["newly_at_risk"]
    assert client.post(f'/api/versions/{p["id"]}/activate').status_code == 200
    assert (
        client.post(
            "/api/execution/events",
            json=payload(client, operation="B/B1/10", at="2026-09-07T10:05"),
        ).status_code
        == 422
    )
    assert len(client.get("/api/execution").json()["events"]) == 4


def test_invalid_balances_rollback_all_changes(client):
    login(client)
    finish_order(client)
    before = client.get("/api/factory").json()
    body = reconciliation(client)
    body["balances"][0]["reserved"] = 1001
    assert client.post("/api/execution/reconcile", json=body).status_code == 422
    assert client.get("/api/factory").json() == before
    assert client.get("/api/execution").json()["closures"] == []
    assert (
        client.post(
            "/api/execution/reconcile", json={**body, "balances": []}
        ).status_code
        == 422
    )


def test_closed_orders_and_clock_cannot_be_reopened(client):
    login(client)
    finish_order(client)
    assert (
        client.post("/api/execution/reconcile", json=reconciliation(client)).status_code
        == 200
    )
    d = client.get("/api/factory").json()
    next(o for o in d["factory"]["orders"] if o["id"] == "A")["status"] = "NEW"
    assert (
        client.put(
            "/api/factory", json={"factory": d["factory"], "revision": d["revision"]}
        ).status_code
        == 409
    )
    d = client.get("/api/factory").json()
    d["factory"]["settings"]["planning_not_before"] = None
    assert (
        client.put(
            "/api/factory", json={"factory": d["factory"], "revision": d["revision"]}
        ).status_code
        == 409
    )


def test_solver_and_independent_validator_enforce_boundary(factory, base):
    early = CpSatProvider().solve(factory, base)
    factory.settings.planning_not_before = datetime(2026, 9, 7, 12, 0, 30)
    with pytest.raises(ValueError, match="boundary"):
        validate_plan(factory, early)
    later = CpSatProvider().solve(factory, base)
    assert validate_plan(factory, later)
    assert all(o["start"] >= "2026-09-07T12:01" for o in later["operations"])


def test_correction_preserves_history_and_reverts_state(client):
    login(client)
    first = event(client).json()["event_id"]
    last = event(client, kind="PROGRESS", quantity=40, at="2026-09-07T08:20").json()[
        "event_id"
    ]
    body = {
        "revision": client.get("/api/execution").json()["revision"],
        "reason": "Incorrect quantity entered",
    }
    assert (
        client.post(f"/api/execution/events/{first}/void", json=body).status_code == 409
    )
    login(client, "supervisor")
    assert (
        client.post(f"/api/execution/events/{last}/void", json=body).status_code == 403
    )
    login(client)
    assert (
        client.post(f"/api/execution/events/{last}/void", json=body).status_code == 200
    )
    d = client.get("/api/execution").json()
    assert (
        len(d["events"]) == 2
        and d["events"][-1]["correction"]["reason"] == body["reason"]
    )
    assert (
        next(o for o in d["operations"] if o["id"] == "A/B1/10")["quantity_completed"]
        == 0
    )
    assert (
        client.post(
            f"/api/execution/events/{first}/void",
            json={**body, "revision": d["revision"]},
        ).status_code
        == 200
    )
    assert not client.get("/api/execution").json()["pending_orders"]
    assert client.post("/api/plan").status_code == 200


def test_reconciled_history_cannot_be_voided(client):
    login(client)
    finish_order(client)
    assert (
        client.post("/api/execution/reconcile", json=reconciliation(client)).status_code
        == 200
    )
    d = client.get("/api/execution").json()
    assert (
        client.post(
            f'/api/execution/events/{d["events"][-1]["id"]}/void',
            json={"revision": d["revision"], "reason": "Try to reopen completed work"},
        ).status_code
        == 409
    )
