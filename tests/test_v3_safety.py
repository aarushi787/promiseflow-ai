from copy import deepcopy
from datetime import timedelta
import pytest
from backend.engine import CpSatProvider, compare, windows
from backend.models import Factory, Window
from backend.scenarios import apply_scenario, Scenario
from backend.validation import validate_plan
from backend.imports import safe_cell


def test_quality_hold_never_auto_releases(factory, base):
    changed = apply_scenario(
        factory, Scenario(kind="quality_hold", target="MAT", hours=1), base
    )
    assert changed.materials[0].stock == factory.materials[0].stock
    assert changed.materials[0].safety_stock == factory.materials[0].safety_stock
    result = CpSatProvider().solve(changed, base + timedelta(days=30))
    assert len(result["blocked"]) == 2 and not result["operations"]


def test_held_order_remains_a_blocked_commitment(factory, base):
    factory.orders[0].status = "ON HOLD"
    result = CpSatProvider().solve(factory, base)
    assert result["blocked"]["A"]
    assert (
        next(o for o in result["orders"] if o["id"] == "A")["status"] == "UNSCHEDULED"
    )


def test_overtime_preserves_lunch_break(factory, base):
    factory.calendars[0].shifts = [[480, 720], [780, 960]]
    changed = apply_scenario(
        factory, Scenario(kind="overtime", target="M1", hours=2), base
    )
    assert changed.calendars[-1].shifts == [[480, 720], [780, 1080]]
    assert factory.calendars[0].shifts == [[480, 720], [780, 960]]


def test_invalid_extension_not_silently_clamped(factory, base):
    with pytest.raises(ValueError):
        apply_scenario(factory, Scenario(kind="overtime", target="M1", hours=10), base)


@pytest.mark.parametrize("field", ["materials", "alternatives"])
def test_duplicate_consumption_or_capability_rejected(factory, field):
    data = factory.model_dump()
    rows = (
        data["products"][0]["materials"]
        if field == "materials"
        else data["routings"][0]["operations"][0]["alternatives"]
    )
    rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError):
        Factory.model_validate(data)


def test_fractional_arrival_and_downtime_round_safely(factory, base):
    material = factory.materials[0]
    material.stock = 0
    material.incoming = 200
    material.arrival = base + timedelta(hours=8, seconds=30)
    result = CpSatProvider().solve(factory, base)
    assert min(o["start"] for o in result["operations"]) >= "2026-09-07T08:01"
    spans = windows(
        factory.calendars[0],
        [Window(start=base + timedelta(hours=8), end=material.arrival)],
        base,
        1440,
    )
    assert spans[0][0] == 481
    assert validate_plan(factory, result)


def test_impacts_include_worsening_and_removed():
    old = dict(
        orders=[
            dict(id="A", completion="2026-09-07T09:00", status="AT RISK"),
            dict(id="B", completion="2026-09-07T09:00", status="ON TIME"),
        ]
    )
    new = dict(orders=[dict(id="A", completion="2026-09-08T09:00", status="LATE")])
    result = compare(old, new)
    assert result["newly_at_risk"] == 2
    assert result["impacts"][1]["after_status"] == "REMOVED"


@pytest.mark.parametrize("mutation", ["identity", "classification"])
def test_independent_validator_rejects_forged_results(factory, base, mutation):
    result = CpSatProvider().solve(factory, base)
    if mutation == "identity":
        result["operations"][0]["job_id"] = "B/B1"
    else:
        result["orders"][0]["status"] = "LATE"
    with pytest.raises(ValueError):
        validate_plan(factory, result)


def test_hard_deadline_is_hard(factory, base):
    factory.orders[0].hard_deadline = base + timedelta(hours=8)
    result = CpSatProvider().solve(factory, base)
    assert result["solver_status"] == "INFEASIBLE"
    assert len(result["orders"]) == 2


def test_old_due_date_not_artificially_infeasible(factory, base):
    result = CpSatProvider().solve(factory, base + timedelta(days=365))
    assert result["solver_status"] in ("FEASIBLE", "OPTIMAL")
    assert all(o["status"] == "LATE" for o in result["orders"])


@pytest.mark.parametrize("value", ["=1+1", "  =HYPERLINK(1)", "\t@SUM(1)", "\r+1"])
def test_export_formula_injection(value):
    assert safe_cell(value).startswith("'")


def test_production_database_rejected_in_demo(tmp_path):
    from backend.store import Store
    from backend.app import create_app
    from fastapi.testclient import TestClient

    path = tmp_path / "production.db"
    store = Store(path)
    with store.connect() as db:
        db.execute("INSERT INTO meta VALUES ('mode','production')")
    with pytest.raises(RuntimeError, match="mode mismatch"):
        with TestClient(create_app(path)):
            pass
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
