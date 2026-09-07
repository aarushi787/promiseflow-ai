"""Independent schedule validator used before activation and by regression tests."""

import math
from collections import defaultdict
from datetime import datetime
from .engine import INACTIVE, minute, release_minute, windows


def validate_plan(factory, plan):
    if plan["solver_status"] not in ("FEASIBLE", "OPTIMAL"):
        raise ValueError("No feasible solution to validate")
    if plan.get("blocked"):
        raise ValueError("Active orders remain unscheduled")
    base = datetime.fromisoformat(plan["base"])
    horizon = factory.settings.horizon_days * 1440
    resources = {r.id: r for r in factory.resources}
    calendars = {c.id: c for c in factory.calendars}
    aux = {a.id: a for a in factory.auxiliaries}
    orders = {o.id: o for o in factory.orders if o.status not in INACTIVE}
    products = {p.id: p for p in factory.products}
    routes = {r.id: r for r in factory.routings}
    occupancy = defaultdict(list)
    tasks = defaultdict(list)
    seen = set()
    expected = set()
    for order in orders.values():
        p = products[order.product_id]
        for batch in range(math.ceil(order.quantity / p.batch_size)):
            for op in routes[p.routing_id].operations:
                expected.add(f"{order.id}/B{batch+1}/{op.id}")
    for row in plan["operations"]:
        if row["id"] in seen:
            raise ValueError("Duplicate scheduled operation")
        seen.add(row["id"])
        if row["order_id"] not in orders:
            raise ValueError("Scheduled order is not active")
        order = orders[row["order_id"]]
        if order.status == "ON HOLD":
            raise ValueError("Cannot schedule an order on hold")
        p = products[order.product_id]
        routing = routes[p.routing_id]
        op = next((x for x in routing.operations if x.id == row["operation_id"]), None)
        if not op or row["resource_id"] not in resources:
            raise ValueError("Unknown operation or resource")
        r = resources[row["resource_id"]]
        alt = next((a for a in op.alternatives if a.resource_id == r.id), None)
        if not alt:
            raise ValueError("Ineligible resource")
        batch = int(row["job_id"].rsplit("/B", 1)[1])
        if (
            batch < 1
            or row["job_id"] != f"{order.id}/B{batch}"
            or row["id"] != f"{row['job_id']}/{op.id}"
            or row["product_id"] != order.product_id
            or row["customer_id"] != order.customer_id
            or row["sequence"] != op.sequence
        ):
            raise ValueError("Inconsistent operation identity")
        quantity = min(p.batch_size, order.quantity - (batch - 1) * p.batch_size)
        if row["quantity"] != quantity:
            raise ValueError("Scheduled quantity does not match transfer batch")
        start_date, end_date = datetime.fromisoformat(
            row["start"]
        ), datetime.fromisoformat(row["end"])
        if any(d.tzinfo or d.second or d.microsecond for d in (start_date, end_date)):
            raise ValueError("Scheduled timestamps must be plant-local whole minutes")
        s = minute(start_date, base)
        e = minute(end_date, base)
        duration = (
            alt.setup_minutes
            + math.ceil(quantity * alt.cycle_minutes / r.efficiency)
            + alt.external_lead_minutes
            + alt.transit_minutes
        )
        if e - s != duration or row["duration"] != duration:
            raise ValueError("Incorrect operation duration")
        if s < max(0, release_minute(order.order_date, base)):
            raise ValueError("Operation starts before release")
        if factory.settings.planning_not_before and s < release_minute(
            factory.settings.planning_not_before, base
        ):
            raise ValueError("Operation starts before the reconciled planning boundary")
        if r.status == "UNAVAILABLE" or (
            r.status in ("BREAKDOWN", "MAINTENANCE") and not r.unavailable
        ):
            raise ValueError("Resource unavailable")
        if not any(
            a <= s and e <= b
            for a, b in windows(calendars[r.calendar_id], r.unavailable, base, horizon)
        ):
            raise ValueError("Operation outside resource calendar")
        occupancy[("resource", r.id)].append((s, e))
        tasks[row["job_id"]].append(
            (op.sequence, s, e, op.transfer_minutes + op.queue_minutes)
        )
        if row.get("tool_id") != op.tool_id:
            raise ValueError("Missing or incorrect tool")
        if op.required_skill:
            operator = aux.get(row.get("operator_id"))
            if (
                not operator
                or operator.kind != "Operator"
                or operator.skill != op.required_skill
                or (
                    operator.eligible_resources
                    and r.id not in operator.eligible_resources
                )
            ):
                raise ValueError("No qualified operator assigned")
        elif row.get("operator_id"):
            raise ValueError("Unexpected operator reservation")
        for aid in (row.get("tool_id"), row.get("operator_id")):
            if not aid:
                continue
            a = aux[aid]
            if not any(
                x <= s and e <= y
                for x, y in windows(
                    calendars[a.calendar_id], a.unavailable, base, horizon
                )
            ):
                raise ValueError("Auxiliary unavailable")
            occupancy[("auxiliary", aid)].append((s, e))
    if seen != expected:
        raise ValueError("Plan does not cover every required batch operation")
    for key, intervals in occupancy.items():
        capacity = (
            resources[key[1]].capacity if key[0] == "resource" else aux[key[1]].capacity
        )
        changes = sorted(
            [(s, 1) for s, e in intervals] + [(e, -1) for s, e in intervals]
        )
        concurrent = 0
        for _, delta in changes:
            concurrent += delta
            if concurrent > capacity:
                raise ValueError(f"Capacity conflict on {key[1]}")
    for rows in tasks.values():
        ordered = sorted(rows)
        for before, after in zip(ordered, ordered[1:]):
            if after[1] < before[2] + before[3]:
                raise ValueError("Operation precedence violated")
    deliveries = {o["id"]: o for o in plan["orders"]}
    if len(deliveries) != len(plan["orders"]):
        raise ValueError("Duplicate delivery results")
    if set(deliveries) != set(orders):
        raise ValueError("Delivery results missing active orders")
    launches = {}
    material_demands = defaultdict(list)
    for oid, order in orders.items():
        job_rows = [rows for jid, rows in tasks.items() if jid.startswith(oid + "/B")]
        completion = max(
            e + transfer for rows in job_rows for seq, s, e, transfer in rows
        )
        if (
            minute(datetime.fromisoformat(deliveries[oid]["completion"]), base)
            != completion
        ):
            raise ValueError("Incorrect order completion")
        due = minute(order.committed_date or order.requested_date, base)
        expected_status = (
            "LATE"
            if completion > due
            else (
                "AT RISK"
                if due - completion < factory.settings.risk_buffer_hours * 60
                else "ON TIME"
            )
        )
        delivery = deliveries[oid]
        if (
            delivery["status"] != expected_status
            or delivery["slack_minutes"] != due - completion
            or delivery["tardiness_minutes"] != max(0, completion - due)
            or minute(datetime.fromisoformat(delivery["due"]), base) != due
        ):
            raise ValueError("Incorrect delivery classification")
        if order.hard_deadline and completion > minute(order.hard_deadline, base):
            raise ValueError("Hard deadline violated")
        launches[oid] = min(s for rows in job_rows for seq, s, e, t in rows)
        for req in products[order.product_id].materials:
            material_demands[req.material_id].append(
                (launches[oid], order.quantity * req.per_unit)
            )
    for material in factory.materials:
        if material.quality_hold and material_demands[material.id]:
            raise ValueError("Held material cannot be consumed")
        consumed = 0
        for launch, demand in sorted(material_demands[material.id]):
            consumed += demand
            supply = max(0, material.stock - material.reserved - material.safety_stock)
            if material.arrival and release_minute(material.arrival, base) <= launch:
                supply += material.incoming
            if consumed > supply + 1e-6:
                raise ValueError(f"Material {material.id} consumed before available")
    return True
