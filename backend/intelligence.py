"""Deterministic decision context. Completeness is not a probability of delivery."""

from datetime import datetime, timedelta
from .engine import INACTIVE, minute, windows


def readiness(factory, base, checked_at=None):
    checked_at = checked_at or datetime.now()
    settings = factory.settings
    confirmed = settings.data_confirmed_at
    age = (checked_at - confirmed).total_seconds() / 3600 if confirmed else None
    warnings = []
    if age is None:
        warnings.append(
            "Operational data has not been confirmed; freshness is unknown."
        )
    elif age < 0 or age > settings.freshness_hours:
        warnings.append(
            "Operational confirmation is stale or future-dated; reconfirm the factory inputs."
        )
    if base.date() < checked_at.date():
        warnings.append(
            "Planning starts in the past. Reconcile actual progress before making a live commitment."
        )
    operations = [o for r in factory.routings for o in r.operations]
    held = [o.id for o in factory.orders if o.status == "ON HOLD"]
    held_material = [m.id for m in factory.materials if m.quality_hold]
    if held or held_material:
        warnings.append("Quality/order holds prevent a complete publishable plan.")
    checks = [
        {
            "name": "Orders",
            "status": "Valid" if factory.orders else "Missing",
            "detail": f"{len(factory.orders)} supplied; {len(held)} on hold",
        },
        {
            "name": "Routings and cycle times",
            "status": "Valid" if operations else "Missing",
            "detail": f"{len(operations)} operation definitions; positive cycle times required",
        },
        {
            "name": "Resources and calendars",
            "status": "Valid" if factory.resources and factory.calendars else "Missing",
            "detail": "References, shifts and holidays validated",
        },
        {
            "name": "Materials",
            "status": "Configured" if factory.materials else "Not modeled",
            "detail": f"{len(held_material)} material holds; supply feasibility evaluated during solve",
        },
        {
            "name": "Operators",
            "status": (
                "Enabled"
                if any(o.required_skill for o in operations)
                else "Not modeled"
            ),
            "detail": "Only explicitly required skills constrain the schedule",
        },
        {
            "name": "Tools",
            "status": (
                "Enabled" if any(o.tool_id for o in operations) else "Not modeled"
            ),
            "detail": "Only explicitly required tooling constrains the schedule",
        },
    ]
    assumptions = [
        "All dates are plant-local; each operation occupies a contiguous working window.",
        "Product batch size controls transfer batches; all batches finish before delivery.",
        "Full-order material demand is allocated at first release; one incoming lot per material.",
        "Fixed setup per batch; sequence-dependent cleaning is not modeled.",
        "Only supplied resource and routing costs are included; revenue is not profit.",
        "New resource hourly rates default to 450 INR, efficiency to 100%, and alternative setup to 30 minutes when omitted. Verify these defaults before relying on estimates.",
        "Manual actuals require whole-order completion and material reconciliation before replanning. Partial-work optimization and live machine feeds are not connected.",
    ]
    return dict(
        checks=checks,
        warnings=warnings,
        assumptions=assumptions,
        source=settings.data_source,
        confirmed_at=confirmed.isoformat() if confirmed else None,
        status="Review required" if warnings else "Inputs confirmed",
        confidence="Based on supplied planning data; not a delivery probability",
    )


def add_costs(original, proposed, result, scenario_kind=None, target=None):
    """Measure work outside the original calendar; never premium-charge all work."""
    premium_minutes = 0
    base = datetime.fromisoformat(result["base"])
    if scenario_kind in ("overtime", "additional_shift"):
        resource = next(r for r in original.resources if r.id == target)
        calendar = next(c for c in original.calendars if c.id == resource.calendar_id)
        spans = windows(
            calendar, resource.unavailable, base, original.settings.horizon_days * 1440
        )
        for op in result["operations"]:
            if op["resource_id"] != target:
                continue
            start, end = minute(datetime.fromisoformat(op["start"]), base), minute(
                datetime.fromisoformat(op["end"]), base
            )
            regular = sum(max(0, min(end, b) - max(start, a)) for a, b in spans)
            premium_minutes += end - start - regular
    premium = round(premium_minutes / 60 * original.settings.overtime_cost_per_hour, 2)
    result["cost_breakdown"] = dict(
        production=result["cost"],
        overtime_minutes=premium_minutes,
        overtime_rate=original.settings.overtime_cost_per_hour,
        overtime_premium=premium,
        total=round(result["cost"] + premium, 2),
        unpriced=[
            "Expedite quote",
            "Transport premium",
            "Late penalties",
            "Unconfigured labour",
        ],
        basis="Resource occupied hours × hourly rate + routing unit cost × quantity; overtime premium on additional calendar minutes only",
    )
    return result


def delivery_risks(factory, result):
    evidence = result.get("evidence", {})
    return [
        dict(
            **o,
            risk_state=(
                "BLOCKED"
                if o["status"] == "UNSCHEDULED"
                else (
                    "LATE"
                    if o["status"] == "LATE"
                    else "WATCH" if o["status"] == "AT RISK" else "ON TRACK"
                )
            ),
            contributors=[
                o.get("reason") or f"Delivery buffer: {o.get('slack_minutes')} minutes",
                *[x["cause"] for x in evidence.get(o["id"], [])],
            ],
        )
        for o in result.get("orders", [])
    ]


def material_impact(factory, result):
    outcomes = {o["id"]: o for o in (result or {}).get("orders", [])}
    rows = []
    for material in factory.materials:
        products = [
            p
            for p in factory.products
            if any(m.material_id == material.id for m in p.materials)
        ]
        ids = {p.id for p in products}
        orders = [
            o
            for o in factory.orders
            if o.product_id in ids and o.status not in INACTIVE
        ]
        rows.append(
            dict(
                material_id=material.id,
                description=material.description,
                supplier_id=material.supplier_id,
                quality_hold=material.quality_hold,
                available=max(
                    0, material.stock - material.reserved - material.safety_stock
                ),
                incoming=material.incoming,
                arrival=material.arrival,
                products=[p.id for p in products],
                orders=[
                    dict(
                        id=o.id,
                        customer_id=o.customer_id,
                        quantity=o.quantity,
                        status=outcomes.get(o.id, {}).get("status", "UNPLANNED"),
                    )
                    for o in orders
                ],
            )
        )
    return rows


def resource_load(factory, result):
    base = datetime.fromisoformat(result["base"])
    calendars = {c.id: c for c in factory.calendars}
    rows = []
    for resource in factory.resources:
        available = windows(
            calendars[resource.calendar_id],
            resource.unavailable,
            base,
            factory.settings.horizon_days * 1440,
        )
        if (
            resource.status == "UNAVAILABLE"
            or resource.status in ("BREAKDOWN", "MAINTENANCE")
            and not resource.unavailable
        ):
            available = []
        ops = [o for o in result["operations"] if o["resource_id"] == resource.id]
        cells = []
        for day in range(min(14, factory.settings.horizon_days)):
            start, end = day * 1440, (day + 1) * 1440
            capacity = (
                sum(max(0, min(b, end) - max(a, start)) for a, b in available)
                * resource.capacity
            )
            occupied = [
                (
                    o,
                    max(
                        0,
                        min(minute(datetime.fromisoformat(o["end"]), base), end)
                        - max(minute(datetime.fromisoformat(o["start"]), base), start),
                    ),
                )
                for o in ops
            ]
            busy = sum(n for o, n in occupied)
            utilization = round(100 * busy / capacity, 1) if capacity else None
            cells.append(
                dict(
                    date=(base + timedelta(days=day)).date().isoformat(),
                    capacity_minutes=capacity,
                    occupied_minutes=busy,
                    utilization=utilization,
                    orders=sorted({o["order_id"] for o, n in occupied if n}),
                    state=(
                        "Unavailable"
                        if not capacity
                        else (
                            "Critical"
                            if utilization >= 95
                            else (
                                "High load"
                                if utilization >= 85
                                else "Healthy" if utilization >= 40 else "Underutilized"
                            )
                        )
                    ),
                )
            )
        rows.append(dict(resource_id=resource.id, name=resource.name, days=cells))
    return rows
