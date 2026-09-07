"""Database-local, bounded result cache. A hit never activates a schedule."""

import hashlib
import json
from datetime import datetime, timezone
import ortools
from .engine import MODEL_VERSION


def fingerprint(factory, base, kwargs, revision, active_id):
    payload = dict(
        factory=factory.model_dump(mode="json"),
        base=base.isoformat(),
        options=kwargs,
        revision=revision,
        active_id=active_id,
        solver=ortools.__version__,
        model=MODEL_VERSION,
    )
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def cached_solve(store, provider, factory, base, **kwargs):
    with store.connect() as db:
        revision, active = store.revision(db), store.active_id(db)
        key = fingerprint(factory, base, kwargs, revision, active)
        row = db.execute(
            "SELECT result FROM solve_cache WHERE fingerprint=?", (key,)
        ).fetchone()
    if row:
        result = json.loads(row[0])
        result["cache"]["hit"] = True
        return result
    result = provider(factory, base, **kwargs)
    result["cache"] = dict(
        hit=False,
        fingerprint=key,
        input_revision=revision,
        active_version=active,
        solved_at=datetime.now(timezone.utc).isoformat(),
    )
    if result["solver_status"] in ("FEASIBLE", "OPTIMAL"):
        with store.connect() as db:
            db.execute(
                "INSERT INTO solve_cache VALUES (?,?,?) ON CONFLICT (fingerprint) DO UPDATE SET created_at=excluded.created_at, result=excluded.result",
                (key, result["cache"]["solved_at"], json.dumps(result, default=str)),
            )
            db.execute(
                "DELETE FROM solve_cache WHERE fingerprint NOT IN (SELECT fingerprint FROM solve_cache ORDER BY created_at DESC LIMIT 100)"
            )
    return result
