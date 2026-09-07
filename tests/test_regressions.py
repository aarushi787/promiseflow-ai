import io
from openpyxl import load_workbook
from backend.imports import template, preview
from backend.engine import CpSatProvider
from backend.scenarios import Scenario, apply_scenario
from backend.models import Factory
import pytest


def test_import_preserves_unspecified_commitment_and_material_fields(factory):
    factory.orders[0].committed_date = factory.orders[0].requested_date
    factory.orders[0].notes = "Keep the agreed dispatch slot"
    result = preview("Orders", template("Orders", factory), "orders.xlsx", factory)
    order = next(o for o in result["merged"]["orders"] if o["id"] == "A")
    assert order["notes"] == "Keep the agreed dispatch slot"
    assert order["committed_date"] is not None


def test_routing_template_preserves_external_lead_time(factory):
    alt = factory.routings[0].operations[1].alternatives[0]
    alt.external_lead_minutes = 1000
    alt.transit_minutes = 60
    alt.unit_cost = 14
    result = preview("Routing", template("Routing", factory), "routing.xlsx", factory)
    assert result["valid"], result["errors"]
    updated = result["merged"]["routings"][0]["operations"][1]["alternatives"][0]
    assert (
        updated["external_lead_minutes"] == 1000
        and updated["transit_minutes"] == 60
        and updated["unit_cost"] == 14
    )


def test_explicit_alternative_remains_eligible(factory, base):
    changed = apply_scenario(
        factory, Scenario(kind="alternative_machine", target="M2"), base
    )
    assert all(
        a.resource_id == "M2"
        for op in changed.routings[0].operations
        for a in op.alternatives
    )


def test_outsourcing_requires_qualified_vendor(factory, base):
    with pytest.raises(ValueError, match="external-vendor"):
        apply_scenario(factory, Scenario(kind="outsource", target="M1"), base)


def test_delimiter_ids_and_nan_are_rejected(factory):
    data = factory.model_dump()
    data["orders"][0]["id"] = "A/B"
    with pytest.raises(ValueError):
        Factory.model_validate(data)
    data = factory.model_dump()
    data["resources"][0]["efficiency"] = float("nan")
    with pytest.raises(ValueError):
        Factory.model_validate(data)


def test_transfer_batch_scenario_preserves_order_quantity(factory, base):
    changed = apply_scenario(
        factory, Scenario(kind="split_quantity", target="P", quantity=50), base
    )
    assert changed.orders[0].quantity == 100 and changed.products[0].batch_size == 50
    assert len(CpSatProvider().solve(changed, base)["operations"]) == 8
