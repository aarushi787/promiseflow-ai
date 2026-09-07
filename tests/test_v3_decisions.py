import io
import json
import time
from datetime import timedelta
from openpyxl import load_workbook
import pytest
from test_api import client, login
from backend.cache import cached_solve
from backend.engine import CpSatProvider
from backend.store import Store
from backend.imports import template, preview
from backend.intelligence import readiness, add_costs
from backend.scenarios import Scenario, apply_scenario


def test_cache_tracks_inputs_and_revision(tmp_path, factory, base):
    store = Store(tmp_path / "cache.db")
    store.save_factory(factory, 0, "test", "seed")
    calls = []

    def solver(*args, **kwargs):
        calls.append(1)
        return CpSatProvider().solve(*args, **kwargs)

    first = cached_solve(store, solver, factory, base)
    second = cached_solve(store, solver, factory, base)
    assert not first["cache"]["hit"] and second["cache"]["hit"] and len(calls) == 1
    factory.resources[0].efficiency = 0.9
    third = cached_solve(store, solver, factory, base)
    assert third["cache"]["fingerprint"] != first["cache"]["fingerprint"]
    store.save_factory(factory, 1, "test", "change")
    fourth = cached_solve(store, solver, factory, base)
    assert not fourth["cache"]["hit"] and fourth["cache"]["input_revision"] == 2


def test_freshness_explicit_and_not_probability(factory, base):
    assert readiness(factory, base, base)["warnings"]
    factory.settings.data_confirmed_at = base
    assert readiness(factory, base, base)["status"] == "Inputs confirmed"
    assert readiness(factory, base, base + timedelta(days=3))["warnings"]


def test_overtime_only_charges_minutes_outside_original_calendar(factory, base):
    proposed = apply_scenario(
        factory, Scenario(kind="overtime", target="M1", hours=2), base
    )
    result = {
        "base": base.isoformat(),
        "cost": 100,
        "operations": [
            dict(resource_id="M1", start="2026-09-07T15:00", end="2026-09-07T17:00")
        ],
    }
    cost = add_costs(factory, proposed, result, "overtime", "M1")["cost_breakdown"]
    assert cost["overtime_minutes"] == 60
    assert cost["total"] == 100 + factory.settings.overtime_cost_per_hour


@pytest.mark.parametrize(
    "kind", ["Products", "Customers", "Operators", "Tools", "Resources"]
)
def test_extended_template_roundtrip(kind, factory):
    result = preview(kind, template(kind, factory), kind + ".xlsx", factory)
    assert result["valid"], result["errors"]


def test_column_mapping_and_wrong_sheet(factory):
    wb = load_workbook(io.BytesIO(template("Orders", factory)))
    wb["Orders"]["A1"] = "Order No"
    output = io.BytesIO()
    wb.save(output)
    result = preview(
        "Orders", output.getvalue(), "orders.xlsx", factory, {"Order No": "id"}
    )
    assert result["valid"]
    with pytest.raises(ValueError, match="sheet named"):
        preview("Materials", output.getvalue(), "orders.xlsx", factory)


def test_import_rollback_restores_only_without_intervening_edits(client):
    login(client)
    before = client.get("/api/factory").json()
    content = client.get("/api/templates/Orders").content
    result = client.post(
        "/api/imports/Orders/preview", files={"file": ("orders.xlsx", content)}
    ).json()
    assert client.post(f'/api/imports/{result["id"]}/apply').status_code == 200
    assert client.post(f'/api/imports/{result["id"]}/rollback').status_code == 200
    restored = client.get("/api/factory").json()
    assert (
        restored["factory"] == before["factory"]
        and restored["active_version"] == before["active_version"]
    )
    assert client.post(f'/api/imports/{result["id"]}/rollback').status_code == 409


def test_rejected_proposal_cannot_publish(client):
    login(client)
    version = client.post("/api/plan").json()["id"]
    assert (
        client.post(
            f"/api/versions/{version}/decision",
            json={"action": "REJECTED", "reason": "Unacceptable customer impact"},
        ).status_code
        == 200
    )
    assert client.post(f"/api/versions/{version}/activate").status_code == 409
    evidence = client.get(f"/api/versions/{version}/report").json()
    assert evidence["decisions"][0]["action"] == "REJECTED"


def test_background_job_and_permissions(client):
    login(client, "sales")
    assert client.post("/api/jobs", json={"kind": "plan"}).status_code == 403
    order = client.get("/api/factory").json()["factory"]["orders"][0]
    order["id"] = "BACKGROUND"
    response = client.post("/api/jobs", json={"kind": "promise", "payload": order})
    assert response.status_code == 202
    jid = response.json()["job_id"]
    for _ in range(100):
        job = client.get(f"/api/jobs/{jid}").json()
        if job["status"] not in ("QUEUED", "RUNNING"):
            break
        time.sleep(0.05)
    assert job["status"] == "COMPLETED", job
    assert job["result"]["candidate"]["id"] == "BACKGROUND"
    assert client.get("/api/factory").json()["active_version"] == 1
    login(client, "purchase")
    assert client.get(f"/api/jobs/{jid}").status_code == 404
