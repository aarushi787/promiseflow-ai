"""Append-only actuals and conservative whole-order reconciliation.

Partial work is recorded, never converted to invented remaining processing times.
Until all observed work is closed and inventory confirmed, replanning fails closed.
"""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Literal
from pydantic import Field, model_validator
from .models import Model, Factory
from .store import Conflict, dumps, now


class ActualEvent(Model):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    revision: int = Field(ge=0)
    version_id: int = Field(gt=0)
    operation_id: str = Field(min_length=1, max_length=250)
    kind: Literal[
        "START", "PROGRESS", "PAUSE", "BREAKDOWN", "HOLD", "RESUME", "COMPLETE"
    ]
    occurred_at: datetime
    quantity_completed: int = Field(ge=0)
    reason: str = Field(min_length=5, max_length=1000)

    @model_validator(mode="after")
    def local_time(self):
        if (
            self.occurred_at.tzinfo
            or self.occurred_at.second
            or self.occurred_at.microsecond
        ):
            raise ValueError("Use plant-local time in whole minutes")
        return self


class Balance(Model):
    material_id: str
    stock: float = Field(ge=0)
    reserved: float = Field(ge=0)
    incoming: float = Field(ge=0)
    arrival: datetime | None = None


class Reconcile(Model):
    revision: int = Field(ge=0)
    reason: str = Field(min_length=5, max_length=1000)
    balances: list[Balance]


class Correction(Model):
    revision: int = Field(ge=0)
    reason: str = Field(min_length=5, max_length=1000)


def local_now(factory):
    return datetime.now(ZoneInfo(factory.settings.timezone)).replace(tzinfo=None)


def ledger(db):
    rows = db.execute("SELECT * FROM actual_events ORDER BY id").fetchall()
    events = [{**dict(r), "body": json.loads(r["body"])} for r in rows]
    corrections = {
        r["event_id"]: dict(r) for r in db.execute("SELECT * FROM actual_corrections")
    }
    states = {}
    for event in events:
        event["correction"] = corrections.get(event["id"])
        if event["correction"]:
            continue
        b = event["body"]
        key = b["operation_id"]
        state = states.setdefault(
            key, {"status": "NOT STARTED", "quantity_completed": 0}
        )
        if b["kind"] == "START":
            state["actual_start"] = b["occurred_at"]
        state.update(
            status=(
                "RUNNING" if b["kind"] in ("START", "PROGRESS", "RESUME") else b["kind"]
            ),
            quantity_completed=b["quantity_completed"],
            last_at=b["occurred_at"],
            order_id=event["order_id"],
            version_id=b["version_id"],
        )
        if b["kind"] == "COMPLETE":
            state["actual_finish"] = b["occurred_at"]
    closed = {r[0] for r in db.execute("SELECT order_id FROM execution_closures")}
    pending = sorted({s["order_id"] for s in states.values()} - closed)
    return events, states, pending


def assert_reconciled(db):
    if ledger(db)[2]:
        raise Conflict(
            "Shop-floor actuals need reconciliation. Complete observed orders and confirm material balances in Shop Floor before planning or publishing. Partial-work rescheduling is not yet supported."
        )


def view(store):
    with store.connect() as db:
        db.execute("BEGIN")
        events, states, pending = ledger(db)
        active = store.version(db=db)
        rows = []
        for op in (active or {}).get("result", {}).get("operations", []):
            state = states.get(
                op["id"], {"status": "NOT STARTED", "quantity_completed": 0}
            )
            rows.append(
                {
                    **op,
                    **state,
                    "remaining_quantity": op["quantity"] - state["quantity_completed"],
                    "finish_variance_minutes": (
                        round(
                            (
                                datetime.fromisoformat(state["actual_finish"])
                                - datetime.fromisoformat(op["end"])
                            ).total_seconds()
                            / 60
                        )
                        if state.get("actual_finish")
                        else None
                    ),
                }
            )
        f = store.load(db)
        products = {p.id: p for p in f.products}
        mids = {
            m.material_id
            for o in f.orders
            if o.id in pending
            for m in products[o.product_id].materials
        }
        return dict(
            revision=store.revision(db),
            version_id=active["id"] if active else None,
            operations=rows,
            events=events,
            pending_orders=pending,
            can_reconcile=bool(pending)
            and all(
                r["status"] == "COMPLETE" for r in rows if r["order_id"] in pending
            ),
            materials=[m.model_dump(mode="json") for m in f.materials if m.id in mids],
            closures=[
                dict(r)
                for r in db.execute("SELECT * FROM execution_closures ORDER BY at")
            ],
        )


def record(store, body, actor, role):
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute(
            "SELECT * FROM actual_events WHERE request_id=?", (body.request_id,)
        ).fetchone()
        if previous:
            if previous["actor"] != actor or json.loads(
                previous["body"]
            ) != body.model_dump(mode="json"):
                raise Conflict("This event request ID has already been used")
            return {"ok": True, "event_id": previous["id"], "replayed": True}
        if body.revision != store.revision(db) or body.version_id != store.active_id(
            db
        ):
            raise Conflict(
                "Plan or progress changed. Refresh before recording this event."
            )
        f = store.load(db)
        if body.occurred_at > local_now(f):
            raise ValueError("Actual events cannot be in the future")
        active = store.version(db=db)
        ops = {r["id"]: r for r in active["result"]["operations"]}
        op = ops.get(body.operation_id)
        if not op:
            raise ValueError("Operation is not in the approved plan")
        events, states, pending = ledger(db)
        # One chronological plant log prevents retrospective changes to resource occupancy.
        valid_events = [e for e in events if not e["correction"]]
        if valid_events and body.occurred_at < datetime.fromisoformat(
            valid_events[-1]["body"]["occurred_at"]
        ):
            raise ValueError(
                "Record events in plant-wide chronological order; historical backfill is not supported"
            )
        state = states.get(
            body.operation_id, {"status": "NOT STARTED", "quantity_completed": 0}
        )
        status, qty = state["status"], state["quantity_completed"]
        if body.kind == "START":
            if (
                f.settings.planning_not_before
                and body.occurred_at < f.settings.planning_not_before
            ):
                raise ValueError(
                    "Actual start precedes the reconciled planning boundary"
                )
            if status != "NOT STARTED" or body.quantity_completed != 0:
                raise ValueError(
                    "START requires an unstarted operation and zero completed quantity"
                )

            def canonical(factory):
                return {
                    k: {r["id"]: r for r in v} if isinstance(v, list) else v
                    for k, v in factory.model_dump(mode="json").items()
                }

            if canonical(f) != canonical(Factory.model_validate(active["inputs"])):
                raise Conflict(
                    "Master data differs from the approved inputs. Publish a reconciled plan before starting more work."
                )
            order = next(o for o in f.orders if o.id == op["order_id"])
            if body.occurred_at < order.order_date:
                raise ValueError("Actual start precedes the order release")
            for pred in ops.values():
                if pred["job_id"] == op["job_id"] and pred["sequence"] < op["sequence"]:
                    ps = states.get(pred["id"], {})
                    if ps.get(
                        "status"
                    ) != "COMPLETE" or body.occurred_at < datetime.fromisoformat(
                        ps["actual_finish"]
                    ) + timedelta(
                        minutes=pred.get("transfer_minutes", 0)
                    ):
                        raise ValueError(
                            "Preceding batch operations and transfer time must be complete"
                        )
        elif body.kind == "RESUME":
            if (
                status not in ("PAUSE", "BREAKDOWN", "HOLD")
                or body.quantity_completed != qty
            ):
                raise ValueError(
                    "RESUME requires paused work and unchanged completed quantity"
                )
            if status == "HOLD" and role not in ("manager", "admin"):
                raise Conflict("A manager must authorize release of held work")
        elif status != "RUNNING":
            raise ValueError("This event requires a running operation")
        if (
            body.kind == "PROGRESS"
            and not qty < body.quantity_completed < op["quantity"]
        ):
            raise ValueError(
                "Progress must increase cumulative quantity; use COMPLETE for the full batch"
            )
        if body.kind == "COMPLETE" and body.quantity_completed != op["quantity"]:
            raise ValueError("COMPLETE requires the full planned batch quantity")
        if body.kind == "COMPLETE" and body.occurred_at <= datetime.fromisoformat(
            state["actual_start"]
        ):
            raise ValueError("Actual finish must be after actual start")
        if (
            body.kind in ("PAUSE", "BREAKDOWN", "HOLD")
            and body.quantity_completed != qty
        ):
            raise ValueError("Record quantity progress separately before pausing")
        if body.kind in ("START", "RESUME"):
            capacities = {r.id: r.capacity for r in f.resources}
            aux = {a.id: a.capacity for a in f.auxiliaries}
            for field, caps in (
                ("resource_id", capacities),
                ("operator_id", aux),
                ("tool_id", aux),
            ):
                key = op.get(field)
                if (
                    key
                    and sum(
                        1
                        for oid, s in states.items()
                        if s["status"] == "RUNNING"
                        and oid in ops
                        and ops[oid].get(field) == key
                    )
                    >= caps[key]
                ):
                    raise ValueError(f"{key} is occupied by other running work")
        cur = db.execute(
            "INSERT INTO actual_events(request_id,actor,recorded_at,order_id,body) VALUES (?,?,?,?,?)",
            (body.request_id, actor, now(), op["order_id"], body.model_dump_json()),
        )
        db.execute(
            "UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'"
        )
        store.audit(
            db,
            actor,
            "Recorded production actual",
            {
                "event_id": cur.lastrowid,
                "operation": body.operation_id,
                "kind": body.kind,
            },
        )
        return {"ok": True, "event_id": cur.lastrowid, "replayed": False}


def reconcile(store, body, actor):
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if body.revision != store.revision(db):
            raise Conflict("Progress changed. Refresh before reconciliation.")
        events, states, pending = ledger(db)
        if not pending:
            raise ValueError("No observed production to reconcile")
        active = store.version(db=db)
        ops = [o for o in active["result"]["operations"] if o["order_id"] in pending]
        if not ops or any(
            states.get(o["id"], {}).get("status") != "COMPLETE" for o in ops
        ):
            raise Conflict(
                "Every operation of each observed order must be completed. Partial-work rescheduling remains blocked."
            )
        f = store.load(db)
        products = {p.id: p for p in f.products}
        mids = {
            m.material_id
            for o in f.orders
            if o.id in pending
            for m in products[o.product_id].materials
        }
        if (
            len({b.material_id for b in body.balances}) != len(body.balances)
            or {b.material_id for b in body.balances} != mids
        ):
            raise ValueError(
                "Confirm exactly one current balance for every material used by observed orders"
            )
        before = f.model_dump(mode="json")
        for o in f.orders:
            if o.id in pending:
                o.status = "COMPLETED"
        for b in body.balances:
            m = next(m for m in f.materials if m.id == b.material_id)
            for key, value in b.model_dump(exclude={"material_id"}).items():
                setattr(m, key, value)
        boundary = max(
            local_now(f),
            *(datetime.fromisoformat(s["last_at"]) for s in states.values()),
        )
        f.settings.planning_not_before = boundary
        f.settings.planning_start = boundary.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        f = Factory.model_validate(f.model_dump())
        # Closures and inventory balances commit together. No approval snapshot is overwritten.
        for oid in pending:
            db.execute(
                "INSERT INTO execution_closures(order_id,actor,at,reason) VALUES (?,?,?,?)",
                (oid, actor, now(), body.reason),
            )
        store.write_factory(db, f)
        store.audit(
            db,
            actor,
            "Reconciled completed production",
            {
                "orders": pending,
                "reason": body.reason,
                "before_materials": [m for m in before["materials"] if m["id"] in mids],
                "balances": [b.model_dump(mode="json") for b in body.balances],
                "not_before": boundary.isoformat(),
            },
        )
        return {
            "ok": True,
            "completed_orders": pending,
            "planning_not_before": boundary.isoformat(),
        }


def correct(store, event_id, body, actor):
    """Void only the last valid event, preserving it and its correction reason."""
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if body.revision != store.revision(db):
            raise Conflict("Progress changed. Refresh before correcting an event.")
        events, states, pending = ledger(db)
        valid = [e for e in events if not e["correction"]]
        if not valid or valid[-1]["id"] != event_id:
            raise Conflict("Only the latest uncorrected plant event can be voided")
        if valid[-1]["order_id"] not in pending:
            raise Conflict("Reconciled production history cannot be voided")
        db.execute(
            "INSERT INTO actual_corrections VALUES (?,?,?,?)",
            (event_id, actor, now(), body.reason),
        )
        db.execute(
            "UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'"
        )
        store.audit(
            db,
            actor,
            "Voided production actual",
            {"event_id": event_id, "reason": body.reason},
        )
        return {"ok": True}
