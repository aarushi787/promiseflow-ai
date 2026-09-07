from datetime import datetime, timedelta
from pydantic import Field
from typing import Literal
from .models import Model, Order, Factory, Window


class Scenario(Model):
    kind: Literal[
        "breakdown",
        "material_delay",
        "supplier_delay",
        "operator_absence",
        "overtime",
        "additional_shift",
        "maintenance",
        "production_delay",
        "quality_hold",
        "quantity",
        "delivery_date",
        "expedite_material",
        "rush_order",
        "outsource",
        "alternative_machine",
        "split_quantity",
    ]
    target: str = ""
    start: datetime | None = None
    hours: int = Field(default=6, ge=1, le=720)
    quantity: int | None = Field(default=None, ge=1, le=1000000)
    date: datetime | None = None
    order: Order | None = None
    reason: str = Field(default="", max_length=500)


def apply_scenario(factory: Factory, scenario: Scenario, base: datetime):
    f = factory.model_copy(deep=True)
    s = scenario

    def find(table):
        row = next((x for x in getattr(f, table) if x.id == s.target), None)
        if row is None:
            raise ValueError(f"Unknown {table} item: {s.target}")
        return row

    start = s.start or base.replace(hour=8)
    if start.tzinfo or (s.date and s.date.tzinfo):
        raise ValueError("Use plant-local dates without offsets")
    if s.kind in ("breakdown", "maintenance", "production_delay"):
        row = find("resources")
        row.unavailable.append(
            Window(
                start=start,
                end=start + timedelta(hours=s.hours),
                reason=s.reason or s.kind.replace("_", " ").title(),
            )
        )
    elif s.kind == "operator_absence":
        row = find("auxiliaries")
        if row.kind != "Operator":
            raise ValueError("Select a qualified operator or operator crew")
        row.unavailable.append(
            Window(
                start=start,
                end=start + timedelta(hours=s.hours),
                reason="Operator absence",
            )
        )
    elif s.kind in ("material_delay", "expedite_material", "quality_hold"):
        row = find("materials")
        if s.kind == "quality_hold":
            row.quality_hold = True
            row.hold_reason = (
                s.reason
                or "Quality release required; duration is not authorization to release"
            )
        else:
            if not row.incoming:
                raise ValueError("Material has no incoming quantity to adjust")
            row.arrival = (row.arrival or start) + timedelta(
                hours=s.hours if s.kind == "material_delay" else -s.hours
            )
    elif s.kind == "supplier_delay":
        find("suppliers")
        affected = False
        for m in f.materials:
            if m.supplier_id == s.target and m.incoming:
                m.arrival = (m.arrival or start) + timedelta(hours=s.hours)
                affected = True
        for routing in f.routings:
            for op in routing.operations:
                for alt in op.alternatives:
                    if (
                        next(
                            r for r in f.resources if r.id == alt.resource_id
                        ).supplier_id
                        == s.target
                    ):
                        alt.external_lead_minutes += s.hours * 60
                        affected = True
        if not affected:
            raise ValueError(
                "No incoming materials or external operations use this supplier"
            )
    elif s.kind in ("overtime", "additional_shift"):
        row = find("resources")
        original = next(c for c in f.calendars if c.id == row.calendar_id)
        cal = original.model_copy(deep=True)
        cal.id = f"{row.id}-EXTENDED"
        cal.name = f"{row.name} · extended calendar"
        # A scenario changes this resource only; operator availability remains real.
        if s.hours > 8:
            raise ValueError("Shift extension must be at most 8 hours")
        cal.shifts = sorted([list(shift) for shift in original.shifts])
        if cal.shifts[-1][1] + s.hours * 60 > 1440:
            raise ValueError(
                "Extension crosses midnight; configure an approved overnight calendar"
            )
        cal.shifts[-1][1] += s.hours * 60
        if s.kind == "additional_shift":
            cal.weekdays = list(range(7))
        f.calendars = [c for c in f.calendars if c.id != cal.id] + [cal]
        row.calendar_id = cal.id
    elif s.kind == "quantity":
        if s.quantity is None:
            raise ValueError("Quantity is required")
        find("orders").quantity = s.quantity
    elif s.kind == "split_quantity":
        if not s.quantity:
            raise ValueError("Transfer batch quantity is required")
        find("products").batch_size = s.quantity
    elif s.kind in ("outsource", "alternative_machine"):
        resource = find("resources")
        if s.kind == "outsource" and resource.type != "External vendor":
            raise ValueError(
                "Outsourcing requires a qualified external-vendor resource"
            )
        changed = False
        for routing in f.routings:
            for operation in routing.operations:
                eligible = [
                    a for a in operation.alternatives if a.resource_id == resource.id
                ]
                if eligible:
                    operation.alternatives = eligible
                    changed = True
        if not changed:
            raise ValueError(
                "No operation is qualified to use this resource. Configure an eligible alternative in its routing first."
            )
    elif s.kind == "delivery_date":
        if not s.date:
            raise ValueError("New delivery date is required")
        row = find("orders")
        row.requested_date = s.date
        row.committed_date = s.date
    elif s.kind == "rush_order":
        if not s.order:
            raise ValueError("New order is required")
        if any(o.id == s.order.id for o in f.orders):
            raise ValueError("Order number already exists")
        f.orders.append(s.order)
    return Factory.model_validate(f.model_dump())
