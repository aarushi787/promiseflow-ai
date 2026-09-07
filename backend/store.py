"""SQLite unit of work with atomic revisions and immutable schedule snapshots."""

import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .models import Factory

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
    def __init__(self, path=None):
        self.path = str(path or os.environ.get("PROMISEFLOW_DB", "data/promiseflow.db"))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS entities (kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS versions (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, created_by TEXT NOT NULL, reason TEXT NOT NULL, base_id INTEGER, revision INTEGER NOT NULL, result TEXT NOT NULL, inputs TEXT NOT NULL, approved_by TEXT, activated_at TEXT);
            CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, role TEXT NOT NULL, password TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, username TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS imports (id TEXT PRIMARY KEY, actor TEXT NOT NULL, revision INTEGER NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, consumed INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, actor TEXT NOT NULL, version_id INTEGER NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS solve_cache (fingerprint TEXT PRIMARY KEY, created_at TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS import_backups (import_id TEXT PRIMARY KEY, before_data TEXT NOT NULL, applied_revision INTEGER NOT NULL, restored INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS solve_jobs (id TEXT PRIMARY KEY, actor TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL, result TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS actual_events (id INTEGER PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, actor TEXT NOT NULL, recorded_at TEXT NOT NULL, order_id TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS execution_closures (order_id TEXT PRIMARY KEY, actor TEXT NOT NULL, at TEXT NOT NULL, reason TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS actual_corrections (event_id INTEGER PRIMARY KEY REFERENCES actual_events(id), actor TEXT NOT NULL, at TEXT NOT NULL, reason TEXT NOT NULL);
            """)
            db.execute("INSERT OR IGNORE INTO meta VALUES ('revision','0')")
            db.execute("INSERT OR IGNORE INTO meta VALUES ('active','0')")
            db.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version','4')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

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
            "INSERT OR REPLACE INTO meta VALUES ('settings',?)",
            (factory.settings.model_dump_json(),),
        )
        db.execute(
            "UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'"
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
                "INSERT INTO versions(created_at,created_by,reason,base_id,revision,result,inputs) VALUES (?,?,?,?,?,?,?)",
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
            vid = cur.lastrowid
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
