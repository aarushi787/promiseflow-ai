from datetime import datetime, timedelta
import pytest
from backend.engine import CpSatProvider, compare
from backend.models import Window, Factory
from backend.validation import validate_plan
from backend.scenarios import Scenario, apply_scenario

solver = CpSatProvider()


def test_complete_schedule_obeys_independent_validator(factory, base):
    r = solver.solve(factory, base)
    assert r["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(r["operations"]) == 4
    assert validate_plan(factory, r)


def test_deterministic_assignments(factory, base):
    one = solver.solve(factory, base)
    two = solver.solve(factory, base)
    assert one["operations"] == two["operations"]
    assert one["orders"] == two["orders"]


def test_shared_tool_and_operator_do_not_overlap(factory, base):
    r = solver.solve(factory, base)
    ops = sorted([o for o in r["operations"] if o["tool_id"]], key=lambda o: o["start"])
    assert ops[0]["end"] <= ops[1]["start"]
    assert all(o["operator_id"] == "OP" for o in ops)


def test_maintenance_respected_and_alternate_selected(factory, base):
    factory.resources[0].unavailable = [
        Window(start=base, end=base + timedelta(days=10))
    ]
    r = solver.solve(factory, base)
    assert all(o["resource_id"] == "M2" for o in r["operations"])
    assert validate_plan(factory, r)


def test_material_arrival_delays_start(factory, base):
    m = factory.materials[0]
    m.stock = 0
    m.incoming = 200
    m.arrival = base + timedelta(days=2, hours=8)
    r = solver.solve(factory, base)
    assert min(o["start"] for o in r["operations"]) >= "2026-09-09T08:00"
    assert validate_plan(factory, r)


def test_stock_is_not_double_allocated(factory, base):
    factory.materials[0].stock = 100
    r = solver.solve(factory, base)
    assert len(r["blocked"]) == 1
    assert r["orders"][1]["status"] == "UNSCHEDULED"


def test_reservations_and_safety_stock_reduce_supply(factory, base):
    m = factory.materials[0]
    m.stock = 200
    m.reserved = 50
    m.safety_stock = 50
    r = solver.solve(factory, base)
    assert len(r["blocked"]) == 1


def test_missing_qualified_operator_blocks_order(factory, base):
    factory.auxiliaries[1].skill = "Other skill"
    r = solver.solve(factory, base)
    assert len(r["blocked"]) == 2
    assert not r["operations"]


def test_batch_splitting_and_precedence(factory, base):
    factory.orders[0].quantity = 250
    r = solver.solve(factory, base)
    assert len([o for o in r["operations"] if o["order_id"] == "A"]) == 6
    assert validate_plan(factory, r)


def test_shift_too_short_blocks_instead_of_crossing_night(factory, base):
    factory.calendars[0].shifts = [[480, 500]]
    r = solver.solve(factory, base)
    assert r["blocked"] and not r["operations"]


def test_promise_freezes_existing_work(factory, base):
    approved = solver.solve(factory, base)
    candidate = factory.orders[0].model_copy(update={"id": "CAND", "quantity": 100})
    factory.orders.append(candidate)
    result = solver.solve(factory, base, fixed=approved, candidate_id="CAND")
    assert result["solver_status"] in ("FEASIBLE", "OPTIMAL")
    old = {o["id"]: o for o in approved["operations"]}
    for op in result["operations"]:
        if op["id"] in old:
            assert op["start"] == old[op["id"]]["start"]
            assert op["resource_id"] == old[op["id"]]["resource_id"]
    assert result["comparison"]["newly_at_risk"] == 0
    assert validate_plan(factory, result)


def test_released_order_keeps_assignment_after_master_status_change(factory, base):
    old = solver.solve(factory, base)
    factory.orders[0].status = "RELEASED"
    result = solver.solve(factory, base, fixed=old, freeze=False)
    before = [o for o in old["operations"] if o["order_id"] == "A"]
    after = [o for o in result["operations"] if o["order_id"] == "A"]
    assert [(o["start"], o["resource_id"]) for o in before] == [
        (o["start"], o["resource_id"]) for o in after
    ]


def test_scenario_is_copy_and_breakdown_respected(factory, base):
    original = factory.model_dump_json()
    changed = apply_scenario(
        factory,
        Scenario(
            kind="breakdown", target="M1", start=base + timedelta(hours=8), hours=48
        ),
        base,
    )
    result = solver.solve(changed, base)
    assert validate_plan(changed, result)
    assert factory.model_dump_json() == original


def test_validator_rejects_corrupt_duration(factory, base):
    r = solver.solve(factory, base)
    r["operations"][0]["end"] = "2026-09-07T23:00"
    with pytest.raises(ValueError):
        validate_plan(factory, r)


def test_bad_reference_is_rejected(factory):
    data = factory.model_dump()
    data["orders"][0]["product_id"] = "MISSING"
    with pytest.raises(ValueError, match="Unknown products"):
        Factory.model_validate(data)


def test_external_operation_runs_over_midnight(factory, base):
    factory.calendars[0].shifts = [[0, 1440]]
    factory.calendars[0].weekdays = list(range(7))
    factory.routings[0].operations[1].alternatives[0].external_lead_minutes = 2000
    r = solver.solve(factory, base)
    assert validate_plan(factory, r)
    assert any(o["duration"] > 1440 for o in r["operations"])


def test_capacity_two_is_respected(factory, base):
    factory.resources[0].capacity = 2
    factory.resources[1].capacity = 2
    factory.auxiliaries[0].capacity = 2
    factory.auxiliaries[1].capacity = 2
    r = solver.solve(factory, base)
    assert validate_plan(factory, r)


def test_holiday_is_not_scheduled(factory, base):
    factory.calendars[0].holidays = ["2026-09-07"]
    r = solver.solve(factory, base)
    assert min(o["start"] for o in r["operations"]) >= "2026-09-08"


def test_no_solution_is_not_a_false_date_promise(factory, base):
    old = solver.solve(factory, base)
    factory.resources[0].unavailable = [
        Window(start=base, end=base + timedelta(days=21))
    ]
    factory.resources[1].unavailable = [
        Window(start=base, end=base + timedelta(days=21))
    ]
    result = solver.solve(factory, base, fixed=old)
    assert not result["operations"] and len(result["blocked"]) == 2
