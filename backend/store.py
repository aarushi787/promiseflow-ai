"""Database unit of work with atomic revisions and immutable schedule snapshots."""

import hashlib
import json
import secrets
from datetime import datetime, timezone
from .models import Factory
from .database import Database

TABLES = (
    "customers",
    "products",
    "routings",
    "resources",
    "materials",
    "calendars",
    "auxiliaries",
    "suppliers",
    "orders",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def dumps(x):
    return json.dumps(x, ensure_ascii=False, default=str)


class Conflict(Exception):
    pass


class Store:
    def __init__(self, path=None, *, schema=None):
        self.database = Database(path, schema=schema)
        self.path = self.database.path
        self.database.initialize()

    def connect(self):
        return self.database.connect()

    def audit(self, db, actor, action, detail):
        db.execute(
            "INSERT INTO audit(at,actor,action,detail) VALUES (?,?,?,?)",
            (now(), actor, action, dumps(detail)),
        )

    def revision(self, db):
        return int(
            db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
        )

    def active_id(self, db):
        return int(
            db.execute("SELECT value FROM meta WHERE key='active'").fetchone()[0]
        )

    def load(self, db=None):
        if db is None:
            with self.connect() as c:
                return self.load(c)
        rows = db.execute("SELECT kind,body FROM entities ORDER BY kind,id").fetchall()
        if not rows:
            return None
        data = {t: [] for t in TABLES}
        for r in rows:
            data[r["kind"]].append(json.loads(r["body"]))
        data["settings"] = json.loads(
            db.execute("SELECT value FROM meta WHERE key='settings'").fetchone()[0]
        )
        return Factory.model_validate(data)

    def write_factory(self, db, factory):
        from .execution import assert_reconciled

        assert_reconciled(db)
        old = self.load(db)
        if old:
            previous_orders = {o.id: o for o in old.orders}
            new_orders = {o.id: o for o in factory.orders}
            for row in db.execute("SELECT order_id FROM execution_closures"):
                o, p = new_orders.get(row[0]), previous_orders.get(row[0])
                if (
                    not o
                    or not p
                    or o.status not in ("COMPLETED", "DISPATCHED")
                    or (o.product_id, o.quantity) != (p.product_id, p.quantity)
                ):
                    raise Conflict(
                        "Reconciled production cannot be reopened or replaced; use a new order ID for new work"
                    )
            if old.settings.planning_not_before and (
                not factory.settings.planning_not_before
                or factory.settings.planning_not_before
                < old.settings.planning_not_before
            ):
                raise Conflict("The reconciled planning boundary cannot move backwards")
        db.execute("DELETE FROM entities")
        for table in TABLES:
            db.executemany(
                "INSERT INTO entities VALUES (?,?,?)",
                [
                    (table, row.id, row.model_dump_json())
                    for row in getattr(factory, table)
                ],
            )
        db.execute(
            "INSERT INTO meta VALUES ('settings',?) ON CONFLICT (key) DO UPDATE SET value=excluded.value",
            (factory.settings.model_dump_json(),),
        )
        db.execute(
            "UPDATE meta SET value=CAST(CAST(value AS INTEGER)+1 AS TEXT) WHERE key='revision'"
        )

    def save_factory(self, factory, revision, actor, reason):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.revision(db) != revision:
                raise Conflict("Data changed. Reload before saving.")
            self.write_factory(db, factory)
            self.audit(db, actor, reason, {"revision": revision + 1})

    def version(self, vid=None, db=None):
        if db is None:
            with self.connect() as c:
                return self.version(vid, c)
        vid = vid or self.active_id(db)
        row = db.execute("SELECT * FROM versions WHERE id=?", (vid,)).fetchone()
        if not row:
            return None
        value = dict(row)
        for key in ("result", "inputs"):
            value[key] = json.loads(value[key])
        return value

    def snapshot(self):
        with self.connect() as db:
            db.execute("BEGIN")
            return self.load(db), self.revision(db), self.version(db=db)

    def save_version(
        self, factory, result, revision, base_id, actor, reason, event=None
    ):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if revision != self.revision(db) or (base_id or 0) != self.active_id(db):
                raise Conflict(
                    "The active plan or factory data changed while solving. Rerun the simulation."
                )
            from .execution import assert_reconciled

            assert_reconciled(db)
            cur = db.execute(
                "INSERT INTO versions(created_at,created_by,reason,base_id,revision,result,inputs) VALUES (?,?,?,?,?,?,?) RETURNING id",
                (
                    now(),
                    actor,
                    reason,
                    base_id,
                    revision,
                    dumps(result),
                    factory.model_dump_json(),
                ),
            )
            vid = cur.fetchone()[0]
            if event:
                db.execute(
                    "INSERT INTO events VALUES (?,?,?,?,?)",
                    (secrets.token_hex(8), now(), actor, vid, dumps(event)),
                )
            self.audit(
                db, actor, "Proposed schedule", {"version": vid, "reason": reason}
            )
            return vid

    def activate(self, vid, actor):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            from .execution import assert_reconciled

            assert_reconciled(db)
            v = self.version(vid, db)
            if not v:
                raise ValueError("Unknown schedule version")
            if v["activated_at"]:
                raise Conflict(
                    "This version was already activated. Create a new proposal to restore an earlier plan."
                )
            decision = db.execute(
                "SELECT action FROM decisions WHERE version_id=? ORDER BY id DESC LIMIT 1",
                (vid,),
            ).fetchone()
            if decision and decision[0] == "REJECTED":
                raise Conflict(
                    "Proposal was rejected. Create a new proposal for review."
                )
            if v["revision"] != self.revision(db) or (
                v["base_id"] or 0
            ) != self.active_id(db):
                raise Conflict(
                    "This proposal is stale. Recalculate against the current plan and data."
                )
            if v["result"]["solver_status"] not in ("FEASIBLE", "OPTIMAL") or v[
                "result"
            ].get("blocked"):
                raise ValueError(
                    "Only a feasible plan with all active orders scheduled can be activated"
                )
            from .validation import validate_plan

            validate_plan(Factory.model_validate(v["inputs"]), v["result"])
            self.write_factory(db, Factory.model_validate(v["inputs"]))
            db.execute("UPDATE meta SET value=? WHERE key='active'", (str(vid),))
            db.execute(
                "UPDATE versions SET approved_by=?,activated_at=? WHERE id=?",
                (actor, now(), vid),
            )
            self.audit(
                db,
                actor,
                "Activated schedule",
                {"version": vid, "previous": v["base_id"]},
            )
            db.execute(
                "INSERT INTO decisions(version_id,actor,at,action,reason) VALUES (?,?,?,?,?)",
                (vid, actor, now(), "APPROVED", v["reason"]),
            )
            return self.version(vid, db)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return (
        salt
        + ":"
        + hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310000).hex()
    )


def password_matches(password, stored):
    return secrets.compare_digest(password_hash(password, stored.split(":")[0]), stored)
