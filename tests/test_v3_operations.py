import sqlite3
import threading
from backend.backup import backup
from backend.jobs import Jobs
from backend.store import Store
from backend.intelligence import resource_load
from backend.engine import CpSatProvider
import pytest


def test_backup_roundtrip_and_overwrite_protection(tmp_path, factory):
    source, destination = tmp_path / "source.db", tmp_path / "backup.db"
    store = Store(source)
    store.save_factory(factory, 0, "test", "seed")
    backup(source, destination)
    assert Store(destination).load() == store.load()
    with pytest.raises(ValueError):
        backup(source, destination)


def test_heatmap_capacity_accounting(factory, base):
    result = CpSatProvider().solve(factory, base)
    rows = resource_load(factory, result)
    for resource in rows:
        assert all(
            d["occupied_minutes"] <= d["capacity_minutes"] for d in resource["days"]
        )
        assert resource["days"][5]["state"] == "Unavailable"


def test_queued_job_refuses_changed_factory(tmp_path, factory):
    store = Store(tmp_path / "jobs.db")
    store.save_factory(factory, 0, "test", "seed")
    jobs = Jobs(store)
    entered, release = threading.Event(), threading.Event()

    def occupy():
        entered.set()
        release.wait(5)
        return {"ok": True}

    jobs.submit("test", "plan", {}, occupy)
    assert entered.wait(2)
    second = jobs.submit("test", "plan", {}, lambda: {"unexpected": True})
    store.save_factory(factory, 1, "test", "edit")
    release.set()
    jobs.executor.shutdown(wait=True)
    assert jobs.get(second["job_id"], "test")["status"] == "FAILED"
