from fastapi.testclient import TestClient
import pytest
from backend.app import create_app, login_attempts
from backend.engine import CpSatProvider
from backend.store import Store, Conflict


@pytest.fixture
def client(storage_target, factory, base):
    path, schema = storage_target
    store = Store(path, schema=schema)
    store.save_factory(factory, 0, "test", "Initialize")
    result = CpSatProvider().solve(factory, base)
    vid = store.save_version(factory, result, 1, None, "test", "Baseline")
    store.activate(vid, "test")
    login_attempts.clear()
    with TestClient(create_app(path, db_schema=schema)) as client:
        yield client


def login(client, role="manager"):
    r = client.post("/api/login", json={"username": role, "password": "promise-demo"})
    assert r.status_code == 200


def test_authentication_required(client):
    assert client.get("/api/factory").status_code == 401
    assert (
        client.post(
            "/api/login", json={"username": "manager", "password": "incorrect"}
        ).status_code
        == 401
    )


def test_role_enforced_on_backend(client):
    login(client, "sales")
    assert client.post("/api/plan").status_code == 403
    assert client.post("/api/versions/1/activate").status_code == 403


def test_promise_does_not_modify_active_plan(client):
    login(client, "sales")
    before = client.get("/api/factory").json()
    order = {**before["factory"]["orders"][0], "id": "NEW-ORDER", "quantity": 50}
    response = client.post("/api/promise", json=order)
    assert response.status_code == 200, response.text
    after = client.get("/api/factory").json()
    assert after == before
    assert response.json()["id"] != before["active_version"]


def test_explicit_activation_updates_version_and_audit(client):
    login(client)
    before = client.get("/api/factory").json()
    proposal = client.post("/api/plan").json()
    response = client.post(f'/api/versions/{proposal["id"]}/activate')
    assert response.status_code == 200, response.text
    after = client.get("/api/factory").json()
    assert (
        after["active_version"] == proposal["id"]
        and after["revision"] == before["revision"] + 1
    )
    assert client.post(f'/api/versions/{proposal["id"]}/activate').status_code == 409
    assert any(
        a["action"] == "Activated schedule" for a in client.get("/api/audit").json()
    )


def test_stale_proposal_rejected(client):
    login(client)
    proposal = client.post("/api/plan").json()
    snapshot = client.get("/api/factory").json()
    snapshot["factory"]["settings"]["plant_name"] = "Changed"
    assert (
        client.put(
            "/api/factory",
            json={"factory": snapshot["factory"], "revision": snapshot["revision"]},
        ).status_code
        == 200
    )
    assert client.post(f'/api/versions/{proposal["id"]}/activate').status_code == 409


def test_foreign_origin_rejected(client):
    login(client)
    assert (
        client.post(
            "/api/plan", headers={"Origin": "https://untrusted.example"}
        ).status_code
        == 403
    )


def test_import_preview_apply_and_replay_protection(client):
    login(client)
    file = client.get("/api/templates/Orders").content
    before = client.get("/api/factory").json()
    p = client.post(
        "/api/imports/Orders/preview", files={"file": ("orders.xlsx", file)}
    ).json()
    assert p["valid"]
    assert client.get("/api/factory").json() == before
    assert client.post(f'/api/imports/{p["id"]}/apply').status_code == 200
    assert client.post(f'/api/imports/{p["id"]}/apply').status_code == 409


def test_stale_master_revision_rejected(client):
    login(client)
    before = client.get("/api/factory").json()
    body = {"factory": before["factory"], "revision": before["revision"]}
    assert client.put("/api/factory", json=body).status_code == 200
    assert client.put("/api/factory", json=body).status_code == 409


def test_report_and_cookie_security(client):
    login(client)
    assert (
        client.get("/api/reports/delivery")
        .headers["content-type"]
        .startswith("text/csv")
    )
    assert client.get("/api/factory").headers["cache-control"] == "no-store"
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/factory").status_code == 401
