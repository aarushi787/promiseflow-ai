from datetime import datetime
from backend.app import planning_epoch
from backend.models import Settings


def test_planner_can_advance_epoch(factory):
    factory.settings.planning_start = datetime(2026, 9, 14, 8)
    assert planning_epoch(
        factory, {"result": {"base": "2026-09-07T00:00:00"}}
    ) == datetime(2026, 9, 14)
