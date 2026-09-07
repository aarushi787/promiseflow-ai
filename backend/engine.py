"""Finite-capacity, deterministic CP-SAT provider. No language model calls.

Whole transfer batches occupy a contiguous working window. Each batch follows
its routing independently, permitting quantity splitting without overlaps.
"""

import math
import ortools
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Protocol
from ortools.sat.python import cp_model
from .models import Factory

PRIORITY = {"Critical": 8, "High": 4, "Normal": 2, "Low": 1}
INACTIVE = {"COMPLETED", "DISPATCHED", "CANCELLED"}
MODEL_VERSION = "3.1.0"


def minute(value, base):
    return int((value - base).total_seconds() // 60)


def release_minute(value, base):
    return math.ceil((value - base).total_seconds() / 60)


def stamp(value, base):
    return (base + timedelta(minutes=int(value))).isoformat(timespec="minutes")


def windows(calendar, unavailable, base, horizon):
    spans = []
    for day in range(horizon // 1440):
        date = base + timedelta(days=day)
        if (
            date.weekday() not in calendar.weekdays
            or date.date().isoformat() in calendar.holidays
        ):
            continue
        for a, b in calendar.shifts:
            spans.append((day * 1440 + a, day * 1440 + b))
    # Merge adjacent windows, allowing continuous vendor lead times over midnight.
    merged = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    for event in unavailable:
        cut_a, cut_b = minute(event.start, base), release_minute(event.end, base)
        next_spans = []
        for a, b in merged:
            if cut_b <= a or cut_a >= b:
                next_spans.append((a, b))
            else:
                if a < cut_a:
                    next_spans.append((a, cut_a))
                if cut_b < b:
                    next_spans.append((cut_b, b))
        merged = next_spans
    return merged


def intersect(a, b):
    return [(max(x, u), min(y, v)) for x, y in a for u, v in b if max(x, u) < min(y, v)]


def first_slot(domains, duration, earliest, requirements, reservations):
    """Earliest feasible greedy slot, used only as a CP-SAT incumbent hint."""
    for low, high in domains:
        start = max(low, earliest)
        while start <= high:
            jump = None
            for key, capacity in requirements:
                overlaps = [
                    (a, b)
                    for a, b in reservations[key]
                    if a < start + duration and b > start
                ]
                points = sorted({start, *[max(start, a) for a, b in overlaps]})
                for point in points:
                    current = [b for a, b in overlaps if a <= point < b]
                    if len(current) >= capacity:
                        jump = max(jump or start, min(current))
                        break
            if jump is None:
                return start
            start = jump
    return None


class SolverProvider(Protocol):
    def solve(self, factory: Factory, base: datetime, **kwargs) -> dict: ...


class CpSatProvider:
    def solve(self, factory, base, fixed=None, candidate_id=None, freeze=True):
        factory = Factory.model_validate(factory.model_dump())
        base = base.replace(hour=0, minute=0, second=0, microsecond=0)
        h = factory.settings.horizon_days * 1440
        model = cp_model.CpModel()
        res = {r.id: r for r in factory.resources}
        products = {p.id: p for p in factory.products}
        routes = {r.id: r for r in factory.routings}
        cals = {c.id: c for c in factory.calendars}
        customers = {c.id: c for c in factory.customers}
        aux = {a.id: a for a in factory.auxiliaries}
        active = sorted(
            [o for o in factory.orders if o.status not in INACTIVE],
            key=lambda o: (
                -PRIORITY[o.priority] * customers[o.customer_id].priority_weight,
                o.committed_date or o.requested_date,
                o.id,
            ),
        )
        if (
            sum(
                math.ceil(o.quantity / products[o.product_id].batch_size)
                * len(routes[products[o.product_id].routing_id].operations)
                for o in active
            )
            > 1200
        ):
            raise ValueError(
                "MVP limit: 1,200 batch operations per solve. Increase product batch size or reduce planning scope."
            )
        rw = {
            r.id: (
                windows(cals[r.calendar_id], r.unavailable, base, h)
                if r.status != "UNAVAILABLE"
                and not (r.status in ("BREAKDOWN", "MAINTENANCE") and not r.unavailable)
                else []
            )
            for r in res.values()
        }
        aw = {
            a.id: windows(cals[a.calendar_id], a.unavailable, base, h)
            for a in aux.values()
        }
        resource_intervals = defaultdict(list)
        auxiliary_intervals = defaultdict(list)
        fixed_map = {x["id"]: x for x in (fixed or {}).get("operations", [])}
        for order in active:
            for pin in fixed_map.values():
                if (
                    pin["order_id"] == order.id
                    and (
                        freeze
                        or pin.get("locked")
                        or order.status in ("RELEASED", "IN PRODUCTION")
                    )
                    and datetime.fromisoformat(pin["start"]) < base
                ):
                    raise ValueError(
                        "Approved or locked work starts before the selected planning epoch. Reconcile completed work and rebuild the plan before checking new promises."
                    )
        reservations = defaultdict(list)
        pinned_ids = set()
        hint_previous = {}
        order_map = {o.id: o for o in active}
        for pin in fixed_map.values():
            order = order_map.get(pin["order_id"])
            if order and (
                freeze
                or pin.get("locked")
                or order.status in ("RELEASED", "IN PRODUCTION")
            ):
                s = minute(datetime.fromisoformat(pin["start"]), base)
                e = minute(datetime.fromisoformat(pin["end"]), base)
                pinned_ids.add(pin["id"])
                for kind, key in [
                    ("r", pin["resource_id"]),
                    ("a", pin.get("tool_id")),
                    ("a", pin.get("operator_id")),
                ]:
                    if key:
                        reservations[(kind, key)].append((s, e))
        blocked = {}
        evidence = defaultdict(list)
        releases = {}
        # Stock allocation is deterministic and auditable. Existing approved orders
        # retain first claim when a new promise is evaluated.
        materials = {m.id: m for m in factory.materials}
        consumed = defaultdict(float)
        allocation_order = (
            sorted(active, key=lambda o: o.id == candidate_id)
            if candidate_id
            else active
        )
        for order in allocation_order:
            if order.status == "ON HOLD":
                blocked[order.id] = "Order on hold; explicit release is required"
                releases[order.id] = h + 1
                continue
            p = products[order.product_id]
            release = max(
                0,
                release_minute(order.order_date, base),
                (
                    release_minute(factory.settings.planning_not_before, base)
                    if factory.settings.planning_not_before
                    else 0
                ),
            )
            allocation = []
            for req in p.materials:
                m = materials[req.material_id]
                if m.quality_hold:
                    blocked[order.id] = (
                        f"{m.id}: quality hold; {m.hold_reason or 'explicit quality release required'}"
                    )
                    continue
                need = order.quantity * req.per_unit
                free = max(0, m.stock - m.reserved - m.safety_stock)
                total = free + m.incoming
                if consumed[m.id] + need > total + 1e-6:
                    blocked[order.id] = (
                        f"{m.id}: {consumed[m.id]+need-total:g} {m.unit} short after safety stock, reservations and earlier allocations"
                    )
                elif consumed[m.id] + need > free + 1e-6:
                    arrival = (
                        max(0, release_minute(m.arrival, base)) if m.arrival else h + 1
                    )
                    release = max(release, arrival)
                    evidence[order.id].append(
                        dict(
                            kind="Material",
                            cause=f"{m.id} replenishment required before production",
                            minutes=arrival,
                            resource=m.id,
                            action="Expedite the incoming material or confirm additional stock.",
                        )
                    )
                allocation.append((m.id, need))
            if order.id not in blocked:
                for mid, need in allocation:
                    consumed[mid] += need
            releases[order.id] = release
        records = []
        completions = {}
        costs = []
        objectives = []
        for order in active:
            if order.id in blocked:
                continue
            p = products[order.product_id]
            routing = routes[p.routing_id]
            tasks = []
            invalid = None
            for batch in range(math.ceil(order.quantity / p.batch_size)):
                qty = min(p.batch_size, order.quantity - batch * p.batch_size)
                for op in sorted(routing.operations, key=lambda x: x.sequence):
                    oid = f"{order.id}/B{batch+1}/{op.id}"
                    choices = []
                    for alt in op.alternatives:
                        r = res[alt.resource_id]
                        duration = (
                            alt.setup_minutes
                            + math.ceil(qty * alt.cycle_minutes / r.efficiency)
                            + alt.external_lead_minutes
                            + alt.transit_minutes
                        )
                        eligible_operators = (
                            [
                                a
                                for a in aux.values()
                                if a.kind == "Operator"
                                and a.skill == op.required_skill
                                and (
                                    not a.eligible_resources
                                    or r.id in a.eligible_resources
                                )
                            ]
                            if op.required_skill
                            else [None]
                        )
                        for operator in eligible_operators:
                            spans = rw[r.id]
                            if op.tool_id:
                                spans = intersect(spans, aw[op.tool_id])
                            if operator:
                                spans = intersect(spans, aw[operator.id])
                            domains = [
                                [max(a, releases[order.id]), b - duration]
                                for a, b in spans
                                if b - duration >= max(a, releases[order.id])
                            ]
                            if domains:
                                choices.append((alt, r, duration, operator, domains))
                    if not choices:
                        invalid = f"{op.name}: no eligible resource, qualified operator, tool, or contiguous shift window can fit this batch"
                        break
                    tasks.append((batch, qty, op, oid, choices))
                if invalid:
                    break
            if invalid:
                blocked[order.id] = invalid
                continue
            previous = {}
            ends = []
            for batch, qty, op, oid, choices in tasks:
                start = model.new_int_var(0, h, oid + "/start")
                end = model.new_int_var(0, h, oid + "/end")
                if batch in previous:
                    model.add(start >= previous[batch])
                selected = []
                options = []
                hinted = []
                for idx, (alt, r, duration, operator, domains) in enumerate(choices):
                    chosen = model.new_bool_var(oid + f"/choice{idx}")
                    local_start = model.new_int_var_from_domain(
                        cp_model.Domain.from_intervals(domains), oid + f"/local{idx}"
                    )
                    local_end = model.new_int_var(0, h, oid + f"/end{idx}")
                    interval = model.new_optional_interval_var(
                        local_start,
                        duration,
                        local_end,
                        chosen,
                        oid + f"/interval{idx}",
                    )
                    model.add(start == local_start).only_enforce_if(chosen)
                    model.add(end == local_end).only_enforce_if(chosen)
                    resource_intervals[r.id].append(interval)
                    if op.tool_id:
                        auxiliary_intervals[op.tool_id].append(interval)
                    if operator:
                        auxiliary_intervals[operator.id].append(interval)
                    cost = round(duration / 60 * r.cost_per_hour + alt.unit_cost * qty)
                    costs.append(cost * chosen)
                    pin = fixed_map.get(oid)
                    if pin and (
                        freeze
                        or pin.get("locked")
                        or order.status in ("RELEASED", "IN PRODUCTION")
                    ):
                        if pin["resource_id"] != r.id or pin.get("operator_id") != (
                            operator.id if operator else None
                        ):
                            model.add(chosen == 0)
                        else:
                            model.add(
                                start
                                == minute(datetime.fromisoformat(pin["start"]), base)
                            ).only_enforce_if(chosen)
                            model.add(
                                end == minute(datetime.fromisoformat(pin["end"]), base)
                            ).only_enforce_if(chosen)
                    selected.append(chosen)
                    options.append((chosen, r, duration, operator, cost))
                    requirements = [(("r", r.id), r.capacity)]
                    if op.tool_id:
                        requirements.append(
                            (("a", op.tool_id), aux[op.tool_id].capacity)
                        )
                    if operator:
                        requirements.append((("a", operator.id), operator.capacity))
                    if oid in pinned_ids:
                        pin = fixed_map[oid]
                        hs = (
                            minute(datetime.fromisoformat(pin["start"]), base)
                            if pin["resource_id"] == r.id
                            and pin.get("operator_id")
                            == (operator.id if operator else None)
                            else None
                        )
                    else:
                        hs = first_slot(
                            domains,
                            duration,
                            hint_previous.get((order.id, batch), releases[order.id]),
                            requirements,
                            reservations,
                        )
                    if hs is not None and any(a <= hs <= b for a, b in domains):
                        hinted.append(
                            (
                                hs + duration,
                                cost,
                                idx,
                                hs,
                                requirements,
                                local_start,
                                local_end,
                            )
                        )
                model.add_exactly_one(selected)
                if hinted:
                    he, hcost, hidx, hs, requirements, local_start, local_end = min(
                        hinted, key=lambda x: (x[0], x[1], x[2])
                    )
                    model.add_hint(start, hs)
                    model.add_hint(end, he)
                    model.add_hint(local_start, hs)
                    model.add_hint(local_end, he)
                    for idx, chosen in enumerate(selected):
                        model.add_hint(chosen, int(idx == hidx))
                    if oid not in pinned_ids:
                        for key, cap in requirements:
                            reservations[key].append((hs, he))
                    hint_previous[(order.id, batch)] = (
                        he + op.transfer_minutes + op.queue_minutes
                    )
                previous[batch] = end + op.transfer_minutes + op.queue_minutes
                records.append((oid, order, batch, qty, op, start, end, options))
                ends.append(previous[batch])
            completion_limit = h + max(
                op.transfer_minutes + op.queue_minutes for op in routing.operations
            )
            completion = model.new_int_var(
                0, completion_limit, order.id + "/completion"
            )
            model.add_max_equality(completion, ends)
            if order.hard_deadline:
                model.add(completion <= minute(order.hard_deadline, base))
            completions[order.id] = completion
            due = minute(order.committed_date or order.requested_date, base)
            tardy = model.new_int_var(
                0, max(0, completion_limit - due), order.id + "/tardy"
            )
            model.add_max_equality(tardy, [0, completion - due])
            late = model.new_bool_var(order.id + "/late")
            model.add(completion > due).only_enforce_if(late)
            model.add(completion <= due).only_enforce_if(late.Not())
            weight = (
                PRIORITY[order.priority] * customers[order.customer_id].priority_weight
            )
            objectives.extend(
                [
                    weight * factory.settings.late_order_weight * late,
                    weight * factory.settings.tardiness_weight * tardy,
                ]
            )
        for rid, intervals in resource_intervals.items():
            model.add_cumulative(intervals, [1] * len(intervals), res[rid].capacity)
        for aid, intervals in auxiliary_intervals.items():
            model.add_cumulative(intervals, [1] * len(intervals), aux[aid].capacity)
        max_lag = max(
            (
                op.transfer_minutes + op.queue_minutes
                for r in routes.values()
                for op in r.operations
            ),
            default=0,
        )
        makespan = model.new_int_var(0, h + max_lag, "makespan")
        if completions:
            model.add_max_equality(makespan, list(completions.values()))
        else:
            model.add(makespan == 0)
        objective = (
            sum(objectives)
            + factory.settings.makespan_weight * makespan
            + factory.settings.cost_weight * sum(costs)
        )
        # Promise solves explicitly minimize the candidate completion. It is only
        # called with the approved schedule frozen, so existing delivery is protected.
        earliest_mode = bool(candidate_id and freeze and candidate_id in completions)
        model.minimize(completions[candidate_id] if earliest_mode else objective)
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 42
        solver.parameters.max_deterministic_time = 0.3
        solver.parameters.max_time_in_seconds = 30
        status = solver.solve(model)
        status_name = solver.status_name(status)
        result = dict(
            base=base.isoformat(),
            horizon_days=factory.settings.horizon_days,
            solver="Google OR-Tools CP-SAT",
            solver_version=ortools.__version__,
            model_version=MODEL_VERSION,
            solver_parameters={
                "workers": 1,
                "seed": 42,
                "max_deterministic_time": 0.3,
                "max_wall_seconds": 30,
            },
            objective_name=(
                "Earliest candidate completion with approved work fixed"
                if earliest_mode
                else "Weighted delivery, tardiness, makespan and configured cost"
            ),
            hard_constraints=[
                "Capacity",
                "Eligibility",
                "Calendar",
                "Precedence",
                "Material",
                "Quality hold",
                "Qualified operators",
                "Tool capacity",
                "Locked work",
                "Hard deadlines",
            ],
            soft_constraints=[
                "Requested/committed delivery",
                "Makespan",
                "Configured production cost",
            ],
            solver_status=status_name,
            deterministic=solver.wall_time < 29.9,
            optimal=status == cp_model.OPTIMAL,
            operations=[],
            orders=[],
            blocked=blocked,
            evidence=dict(evidence),
            cost=0,
            settings=factory.settings.model_dump(),
            statistics=dict(
                wall_seconds=round(solver.wall_time, 3),
                best_bound=(
                    solver.best_objective_bound
                    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
                    else None
                ),
                objective=(
                    solver.objective_value
                    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
                    else None
                ),
            ),
        )
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            result["message"] = (
                "No feasible schedule found within the planning horizon and solver budget. Check locked work, capacity and calendars; this is not proof of a customer-date impossibility."
            )
            result["orders"] = [
                dict(
                    id=o.id,
                    completion=None,
                    due=stamp(minute(o.committed_date or o.requested_date, base), base),
                    status="UNSCHEDULED",
                    tardiness_minutes=None,
                    slack_minutes=None,
                    reason=blocked.get(o.id, result["message"]),
                )
                for o in active
            ]
            result["comparison"] = compare(fixed, result)
            return result
        for oid, order, batch, qty, op, start, end, options in records:
            chosen, r, duration, operator, cost = next(
                x for x in options if solver.value(x[0])
            )
            s, e = solver.value(start), solver.value(end)
            result["operations"].append(
                dict(
                    id=oid,
                    job_id=f"{order.id}/B{batch+1}",
                    order_id=order.id,
                    product_id=order.product_id,
                    customer_id=order.customer_id,
                    operation=op.name,
                    operation_id=op.id,
                    sequence=op.sequence,
                    resource_id=r.id,
                    operator_id=operator.id if operator else None,
                    tool_id=op.tool_id,
                    quantity=qty,
                    start=stamp(s, base),
                    end=stamp(e, base),
                    duration=duration,
                    cost=cost,
                    priority=order.priority,
                    locked=order.status in ("RELEASED", "IN PRODUCTION"),
                    transfer_minutes=op.transfer_minutes + op.queue_minutes,
                )
            )
            result["cost"] += cost
        for order in active:
            completion = (
                solver.value(completions[order.id]) if order.id in completions else None
            )
            due = minute(order.committed_date or order.requested_date, base)
            status = (
                "UNSCHEDULED"
                if completion is None
                else (
                    "LATE"
                    if completion > due
                    else (
                        "AT RISK"
                        if due - completion < factory.settings.risk_buffer_hours * 60
                        else "ON TIME"
                    )
                )
            )
            result["orders"].append(
                dict(
                    id=order.id,
                    completion=(
                        stamp(completion, base) if completion is not None else None
                    ),
                    due=stamp(due, base),
                    status=status,
                    tardiness_minutes=(
                        max(0, completion - due) if completion is not None else None
                    ),
                    slack_minutes=due - completion if completion is not None else None,
                    reason=blocked.get(order.id),
                )
            )
        result["operations"].sort(key=lambda x: (x["start"], x["resource_id"], x["id"]))
        result["bottlenecks"] = bottlenecks(factory, result, rw, base)
        result["comparison"] = compare(fixed, result)
        result["earliest_proven"] = earliest_mode and result["optimal"]
        return result


def compare(old, new):
    previous = {o["id"]: o for o in (old or {}).get("orders", [])}
    old_ops = {o["id"]: o for o in (old or {}).get("operations", [])}
    impacts = []
    current = {o["id"]: o for o in new.get("orders", [])}
    severity = {
        "ON TIME": 0,
        "WATCH": 1,
        "AT RISK": 2,
        "LATE": 3,
        "UNSCHEDULED": 4,
        "REMOVED": 5,
        "COMPLETED": 0,
    }
    for oid, before in previous.items():
        order = current.get(
            oid,
            {
                "id": oid,
                "completion": None,
                "status": (
                    "COMPLETED"
                    if oid in new.get("completed_order_ids", [])
                    else "REMOVED"
                ),
            },
        )
        delta = None
        if before.get("completion") and order.get("completion"):
            delta = int(
                (
                    datetime.fromisoformat(order["completion"])
                    - datetime.fromisoformat(before["completion"])
                ).total_seconds()
                / 60
            )
        impacts.append(
            dict(
                order_id=order["id"],
                before=before["completion"],
                after=order["completion"],
                delay_minutes=delta,
                before_status=before["status"],
                after_status=order["status"],
                newly_at_risk=severity.get(order["status"], 4)
                > severity.get(before["status"], 4)
                or (order["status"] == "LATE" and delta is not None and delta > 0),
            )
        )
    moved = [
        dict(
            id=o["id"],
            order_id=o["order_id"],
            from_resource=old_ops[o["id"]]["resource_id"],
            to_resource=o["resource_id"],
            before=old_ops[o["id"]]["start"],
            after=o["start"],
        )
        for o in new.get("operations", [])
        if o["id"] in old_ops
        and (
            o["start"] != old_ops[o["id"]]["start"]
            or o["resource_id"] != old_ops[o["id"]]["resource_id"]
        )
    ]
    return dict(
        impacts=impacts,
        moved=moved,
        newly_at_risk=sum(x["newly_at_risk"] for x in impacts),
    )


def bottlenecks(factory, result, rw, base):
    end = 7 * 1440
    rows = []
    for r in factory.resources:
        capacity = (
            sum(max(0, min(b, end) - max(a, 0)) for a, b in rw[r.id]) * r.capacity
        )
        ops = [o for o in result["operations"] if o["resource_id"] == r.id]
        busy = sum(
            max(
                0,
                min(minute(datetime.fromisoformat(o["end"]), base), end)
                - max(0, minute(datetime.fromisoformat(o["start"]), base)),
            )
            for o in ops
        )
        pct = round(busy / capacity * 100, 1) if capacity else 0
        rows.append(
            dict(
                resource_id=r.id,
                name=r.name,
                utilization=pct,
                load_hours=round(busy / 60, 1),
                capacity_hours=round(capacity / 60, 1),
                affected_orders=sorted({o["order_id"] for o in ops}),
                severity="High" if pct >= 85 else "Medium" if pct >= 65 else "Low",
                action=(
                    "Evaluate overtime or alternate eligible resources."
                    if pct >= 65
                    else "Capacity available for eligible operations."
                ),
            )
        )
    return sorted(rows, key=lambda x: -x["utilization"])


def explain(factory, result, order_id):
    order = next((o for o in result.get("orders", []) if o["id"] == order_id), None)
    if not order:
        return [
            dict(
                kind="Solver",
                cause=result.get("message", "Order is not part of this schedule"),
                action="Review the planning scope.",
            )
        ]
    if order.get("reason"):
        return [
            dict(
                kind="Constraint",
                cause=order["reason"],
                action="Correct the constraint and rerun planning.",
            )
        ]
    evidence = list(result.get("evidence", {}).get(order_id, []))
    ops = [o for o in result["operations"] if o["order_id"] == order_id]
    external = {r.id for r in factory.resources if r.type == "External vendor"}
    for rid in sorted({o["resource_id"] for o in ops} & external):
        duration = max(o["duration"] for o in ops if o["resource_id"] == rid)
        evidence.append(
            dict(
                kind="External process",
                resource=rid,
                minutes=duration,
                cause=f"{rid} occupies each batch for {duration/60:.1f} hours, including vendor lead time and transit.",
                action="Confirm vendor turnaround or configure a qualified alternative.",
            )
        )
    for resource in result.get("bottlenecks", [])[:2]:
        if order_id in resource["affected_orders"]:
            evidence.append(
                dict(
                    kind="Resource load",
                    resource=resource["resource_id"],
                    cause=f"{resource['name']} uses {resource['utilization']}% of available capacity in the first seven days.",
                    action=resource["action"],
                )
            )
    if not evidence:
        evidence.append(
            dict(
                kind="Calendar & sequence",
                cause="Completion follows batch precedence, eligible working windows and shared resource reservations.",
                action="Review the operation timeline for available recovery options.",
            )
        )
    return evidence
