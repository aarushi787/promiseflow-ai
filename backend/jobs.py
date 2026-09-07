"""Durable statuses for a bounded, single-process planning worker."""

from concurrent.futures import ThreadPoolExecutor
import json
import secrets
from .store import now, dumps, Conflict


class Jobs:
    def __init__(self, store):
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="planning")

    def submit(self, actor, kind, payload, work):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if (
                db.execute(
                    "SELECT COUNT(*) FROM solve_jobs WHERE status IN ('QUEUED','RUNNING')"
                ).fetchone()[0]
                >= 4
            ):
                raise Conflict(
                    "Planning queue is full; wait for a running request to finish"
                )
            jid = secrets.token_hex(12)
            revision = self.store.revision(db)
            db.execute(
                "INSERT INTO solve_jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    jid,
                    actor,
                    kind,
                    dumps(payload),
                    "QUEUED",
                    now(),
                    now(),
                    revision,
                    None,
                    None,
                ),
            )
        self.executor.submit(self._run, jid, revision, work)
        return {"job_id": jid, "status": "QUEUED"}

    def _run(self, jid, revision, work):
        try:
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if (
                    db.execute(
                        "SELECT status FROM solve_jobs WHERE id=?", (jid,)
                    ).fetchone()[0]
                    == "CANCELLED"
                ):
                    return
                if revision != self.store.revision(db):
                    raise Conflict("Factory changed while queued; submit again")
                db.execute(
                    "UPDATE solve_jobs SET status='RUNNING', updated_at=? WHERE id=?",
                    (now(), jid),
                )
            result = work()
            with self.store.connect() as db:
                db.execute(
                    "UPDATE solve_jobs SET status='COMPLETED', result=?, updated_at=? WHERE id=? AND status='RUNNING'",
                    (dumps(result), now(), jid),
                )
        except Exception as exc:
            detail = (
                str(exc)
                if isinstance(exc, (ValueError, Conflict))
                else getattr(
                    exc, "detail", "Planning failed; retry or contact the administrator"
                )
            )
            with self.store.connect() as db:
                db.execute(
                    "UPDATE solve_jobs SET status='FAILED', error=?, updated_at=? WHERE id=? AND status IN ('QUEUED','RUNNING')",
                    (str(detail), now(), jid),
                )

    def get(self, jid, actor, admin=False):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM solve_jobs WHERE id=?", (jid,)).fetchone()
            if not row or (row["actor"] != actor and not admin):
                return None
            value = dict(row)
            value.pop("payload")
            value["result"] = json.loads(value["result"]) if value["result"] else None
            return value
