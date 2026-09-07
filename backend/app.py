import csv
import hashlib
import io
import json
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Request,
    Response,
    UploadFile,
    File,
    Form,
)
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, ValidationError
from .models import Model, Factory, Order
from .demo import demo_factory
from .engine import CpSatProvider, explain, INACTIVE, compare
from .cache import cached_solve
from .jobs import Jobs
from .intelligence import (
    readiness,
    add_costs,
    delivery_risks,
    material_impact,
    resource_load,
)
from .store import Store, Conflict, password_hash, password_matches, now, dumps
from .scenarios import Scenario, apply_scenario
from .imports import template, preview, safe_cell
from .execution import (
    ActualEvent,
    Reconcile,
    Correction,
    correct as correct_actual,
    assert_reconciled,
    view as execution_view,
    record as record_actual,
    reconcile as reconcile_actuals,
)

SOLVER = CpSatProvider()
solve_lock = threading.Lock()
login_attempts = defaultdict(deque)
DEMO = os.environ.get("PROMISEFLOW_MODE", "demo") == "demo"
ROLES = [
    "planner",
    "sales",
    "manager",
    "supervisor",
    "purchase",
    "maintenance",
    "management",
    "admin",
]
WRITE = {"planner", "manager", "admin"}
APPROVE = {"manager", "admin"}


def solve(*args, **kwargs):
    if not solve_lock.acquire(blocking=False):
        raise HTTPException(429, "Another plan is being calculated. Retry shortly.")
    try:
        return SOLVER.solve(*args, **kwargs)
    finally:
        solve_lock.release()


def planning_epoch(factory, active):
    if factory.settings.planning_start:
        return factory.settings.planning_start.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    return (
        datetime.fromisoformat(active["result"]["base"])
        if active
        else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    )


def create_app(db_path=None):
    store = Store(db_path)
    jobs = Jobs(store)

    def evaluate(factory, base, **kwargs):
        with store.connect() as db:
            assert_reconciled(db)
        result = cached_solve(store, solve, factory, base, **kwargs)
        with store.connect() as db:
            result["completed_order_ids"] = [
                r[0] for r in db.execute("SELECT order_id FROM execution_closures")
            ]
        result["comparison"] = compare(kwargs.get("fixed"), result)
        result["readiness"] = readiness(factory, base)
        return add_costs(factory, factory, result)

    @asynccontextmanager
    async def lifespan(app):
        password = os.environ.get(
            "PROMISEFLOW_ADMIN_PASSWORD", "promise-demo" if DEMO else ""
        )
        if not DEMO and len(password) < 16:
            raise RuntimeError(
                "Set PROMISEFLOW_ADMIN_PASSWORD to at least 16 characters in production"
            )
        with store.connect() as db:
            mode = db.execute("SELECT value FROM meta WHERE key='mode'").fetchone()
            if mode and mode[0] != ("demo" if DEMO else "production"):
                raise RuntimeError(
                    "Database mode mismatch: demo and production must use separate databases"
                )
            if not DEMO and (
                (mode and mode[0] != "production")
                or (
                    not mode and db.execute("SELECT 1 FROM entities LIMIT 1").fetchone()
                )
            ):
                raise RuntimeError(
                    "A demo or unclassified database cannot run in production. Use a new production database and validated imports."
                )
            db.execute(
                "INSERT OR IGNORE INTO meta VALUES ('mode',?)",
                ("demo" if DEMO else "production",),
            )
            for role in (ROLES if DEMO else ["admin"]):
                if not db.execute(
                    "SELECT 1 FROM users WHERE username=?", (role,)
                ).fetchone():
                    db.execute(
                        "INSERT INTO users VALUES (?,?,?)",
                        (role, role, password_hash(password)),
                    )
        with store.connect() as db:
            db.execute(
                "UPDATE solve_jobs SET status='INTERRUPTED', error='Service restarted; submit again', updated_at=? WHERE status IN ('QUEUED','RUNNING')",
                (now(),),
            )
        if not store.load():
            factory = (
                demo_factory()
                if DEMO
                else Factory(
                    customers=[],
                    products=[],
                    routings=[],
                    resources=[],
                    materials=[],
                    calendars=[],
                    orders=[],
                )
            )
            store.save_factory(
                factory,
                0,
                "system",
                "Initialized demo factory" if DEMO else "Initialized factory",
            )
            if DEMO:
                base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                result = SOLVER.solve(factory, base)
                vid = store.save_version(
                    factory,
                    result,
                    1,
                    None,
                    "system",
                    "Initial synthetic demonstration plan",
                )
                if (
                    result["solver_status"] in ("FEASIBLE", "OPTIMAL")
                    and not result["blocked"]
                ):
                    store.activate(vid, "system · demo seed")
        yield
        jobs.executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title="PromiseFlow AI", version="3.1.0", lifespan=lifespan)
    app.state.store = store

    @app.middleware("http")
    async def security(request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            allowed = os.environ.get(
                "PROMISEFLOW_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8017,http://127.0.0.1:8017",
            ).split(",")
            if origin and origin not in allowed:
                return JSONResponse(
                    {"detail": "Origin is not allowed"}, status_code=403
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    def user(request: Request):
        token = request.cookies.get("pf_session", "")
        with store.connect() as db:
            row = db.execute(
                "SELECT u.username,u.role FROM sessions s JOIN users u ON u.username=s.username WHERE s.hash=? AND s.expires>?",
                (hashlib.sha256(token.encode()).hexdigest(), time.time()),
            ).fetchone()
        if not row:
            raise HTTPException(401, "Sign in to continue")
        return dict(row)

    def authorize(u, roles):
        if u["role"] not in roles:
            raise HTTPException(403, "Your role cannot perform this action")

    class Login(Model):
        username: str = Field(max_length=100)
        password: str = Field(max_length=200)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "demo": DEMO, "version": "3.1.0"}

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        key = request.client.host if request.client else "unknown"
        attempts = login_attempts[key]
        while attempts and attempts[0] < time.time() - 60:
            attempts.popleft()
        if len(attempts) >= 12:
            raise HTTPException(429, "Too many sign-in attempts. Wait one minute.")
        attempts.append(time.time())
        with store.connect() as db:
            row = db.execute(
                "SELECT * FROM users WHERE username=?", (body.username,)
            ).fetchone()
            if not row or not password_matches(body.password, row["password"]):
                raise HTTPException(401, "Incorrect username or password")
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode()).hexdigest()
            db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?)",
                (digest, body.username, time.time() + 8 * 3600),
            )
            store.audit(db, body.username, "Signed in", {})
        response.set_cookie(
            "pf_session",
            token,
            httponly=True,
            samesite="strict",
            secure=not DEMO,
            max_age=8 * 3600,
        )
        return {"username": body.username, "role": row["role"], "demo": DEMO}

    @app.get("/api/me")
    def me(u=Depends(user)):
        return {**u, "demo": DEMO}

    @app.post("/api/logout")
    def logout(request: Request, response: Response, u=Depends(user)):
        with store.connect() as db:
            db.execute(
                "DELETE FROM sessions WHERE hash=?",
                (
                    hashlib.sha256(
                        request.cookies.get("pf_session", "").encode()
                    ).hexdigest(),
                ),
            )
        response.delete_cookie("pf_session")
        return {"ok": True}

    @app.get("/api/factory")
    def factory(u=Depends(user)):
        f, rev, active = store.snapshot()
        return dict(
            factory=f.model_dump(mode="json"),
            revision=rev,
            active_version=active["id"] if active else None,
            plan=active["result"] if active else None,
            approved_factory=active["inputs"] if active else None,
            pending_master_changes=bool(active and rev != active["revision"] + 1),
            execution_pending_orders=execution_view(store)["pending_orders"],
            readiness=readiness(f, planning_epoch(f, active)),
        )

    @app.get("/api/readiness")
    def planning_readiness(u=Depends(user)):
        f, rev, active = store.snapshot()
        value = readiness(f, planning_epoch(f, active))
        if execution_view(store)["pending_orders"]:
            value["status"] = "Blocked by unreconciled actuals"
            value["warnings"].append(
                "Complete observed production and reconcile material balances in Shop Floor before planning."
            )
        return value

    @app.get("/api/execution")
    def production_actuals(u=Depends(user)):
        return execution_view(store)

    @app.post("/api/execution/events")
    def production_event(body: ActualEvent, u=Depends(user)):
        authorize(u, WRITE | {"supervisor"})
        return record_actual(store, body, u["username"], u["role"])

    @app.post("/api/execution/reconcile")
    def production_reconciliation(body: Reconcile, u=Depends(user)):
        authorize(u, APPROVE)
        return reconcile_actuals(store, body, u["username"])

    @app.post("/api/execution/events/{event_id}/void")
    def production_correction(event_id: int, body: Correction, u=Depends(user)):
        authorize(u, APPROVE)
        return correct_actual(store, event_id, body, u["username"])

    @app.get("/api/delivery-risks")
    def risks(u=Depends(user)):
        f, rev, active = store.snapshot()
        return (
            delivery_risks(Factory.model_validate(active["inputs"]), active["result"])
            if active
            else []
        )

    @app.get("/api/material-impact")
    def supply_impact(u=Depends(user)):
        f, rev, active = store.snapshot()
        return {
            "revision": rev,
            "active_version": active["id"] if active else None,
            "items": material_impact(f, active["result"] if active else None),
            "note": "Current master dependencies with last approved delivery projections; rebuild after changes.",
        }

    @app.get("/api/resource-load")
    def load_heatmap(u=Depends(user)):
        active = store.version()
        return {
            "version": active["id"] if active else None,
            "items": (
                resource_load(
                    Factory.model_validate(active["inputs"]), active["result"]
                )
                if active
                else []
            ),
        }

    class FactoryUpdate(Model):
        factory: Factory
        revision: int

    @app.put("/api/factory")
    def update(body: FactoryUpdate, u=Depends(user)):
        authorize(u, WRITE)
        store.save_factory(
            body.factory, body.revision, u["username"], "Updated factory master data"
        )
        return {"ok": True}

    @app.post("/api/plan")
    def plan(u=Depends(user)):
        authorize(u, WRITE)
        f, rev, active = store.snapshot()
        base = planning_epoch(f, active)
        result = evaluate(
            f, base, fixed=active["result"] if active else None, freeze=False
        )
        vid = store.save_version(
            f,
            result,
            rev,
            active["id"] if active else None,
            u["username"],
            "Reoptimized production plan",
        )
        return {"id": vid, "result": result}

    @app.post("/api/promise")
    def promise(order: Order, u=Depends(user)):
        authorize(u, WRITE | {"sales"})
        f, rev, active = store.snapshot()
        if any(o.id == order.id for o in f.orders):
            raise ValueError("Use a new order number for a promise check")
        if order.status in INACTIVE or order.status == "ON HOLD":
            raise ValueError("Promise checks require an active order")
        order.committed_date = None
        f.orders.append(order)
        f = Factory.model_validate(f.model_dump())
        base = planning_epoch(f, active)
        result = evaluate(
            f,
            base,
            fixed=active["result"] if active else None,
            candidate_id=order.id,
            freeze=True,
        )
        found = next((o for o in result["orders"] if o["id"] == order.id), None)
        # A late incumbent is not proof that an on-time assignment is impossible.
        status = "AT RISK"
        if found:
            if found["status"] == "ON TIME":
                status = "FEASIBLE"
            elif found["status"] == "UNSCHEDULED" or (
                found["status"] == "LATE" and result.get("earliest_proven")
            ):
                status = "NOT FEASIBLE"
        if status == "FEASIBLE" and (
            result["blocked"]
            or result["readiness"]["warnings"]
            or result.get("comparison", {}).get("newly_at_risk")
        ):
            status = "AT RISK"
        vid = store.save_version(
            f,
            result,
            rev,
            active["id"] if active else None,
            u["username"],
            f"Promise check · {order.id}",
        )
        return dict(
            id=vid,
            result=result,
            promise_status=status,
            candidate=found,
            explanations=explain(f, result, order.id),
            order_id=order.id,
        )

    @app.post("/api/scenario")
    def scenario(s: Scenario, u=Depends(user)):
        authorize(u, WRITE | {"sales", "maintenance", "purchase"})
        f, rev, active = store.snapshot()
        base = planning_epoch(f, active)
        proposed = apply_scenario(f, s, base)
        result = evaluate(
            proposed, base, fixed=active["result"] if active else None, freeze=False
        )
        add_costs(f, proposed, result, s.kind, s.target)
        vid = store.save_version(
            proposed,
            result,
            rev,
            active["id"] if active else None,
            u["username"],
            s.reason or s.kind.replace("_", " ").title(),
            s.model_dump(mode="json"),
        )
        return {"id": vid, "result": result}

    class Recovery(Model):
        kind: str
        target: str = ""

    @app.post("/api/versions/{vid}/recover")
    def recover(vid: int, body: Recovery, u=Depends(user)):
        authorize(u, WRITE | {"sales"})
        v = store.version(vid)
        if not v:
            raise HTTPException(404, "Proposal not found")
        f, rev, active = store.snapshot()
        if v["revision"] != rev or (v["base_id"] or 0) != (
            active["id"] if active else 0
        ):
            raise Conflict("Proposal is stale")
        f = Factory.model_validate(v["inputs"])
        base = datetime.fromisoformat(v["result"]["base"])
        if body.kind == "resequence":
            proposed = f
        else:
            proposed = apply_scenario(
                f,
                Scenario(
                    kind=body.kind,
                    target=body.target,
                    hours=48 if body.kind == "expedite_material" else 4,
                ),
                base,
            )
        result = evaluate(
            proposed, base, fixed=active["result"] if active else None, freeze=False
        )
        add_costs(f, proposed, result, body.kind, body.target)
        newid = store.save_version(
            proposed,
            result,
            rev,
            active["id"] if active else None,
            u["username"],
            f"Recovery · {body.kind} · proposal {vid}",
        )
        return {"id": newid, "result": result}

    @app.get("/api/versions")
    def versions(u=Depends(user)):
        with store.connect() as db:
            return {
                "active": store.active_id(db),
                "items": [
                    dict(r)
                    for r in db.execute(
                        "SELECT id,created_at,created_by,reason,base_id,revision,approved_by,activated_at,(SELECT action FROM decisions d WHERE d.version_id=versions.id ORDER BY d.id DESC LIMIT 1) AS decision_status FROM versions ORDER BY id DESC LIMIT 100"
                    )
                ],
            }

    class JobRequest(Model):
        kind: str = Field(pattern="^(plan|promise|scenario|recovery)$")
        payload: dict = Field(default_factory=dict)
        version_id: int | None = None

    @app.post("/api/jobs", status_code=202)
    def submit_job(body: JobRequest, u=Depends(user)):
        roles = (
            WRITE
            if body.kind == "plan"
            else (
                WRITE | {"sales", "maintenance", "purchase"}
                if body.kind == "scenario"
                else WRITE | {"sales"}
            )
        )
        authorize(u, roles)
        if body.kind == "plan":
            work = lambda: plan(u)
        elif body.kind == "promise":
            parsed = Order.model_validate(body.payload)
            work = lambda: promise(parsed, u)
        elif body.kind == "scenario":
            parsed = Scenario.model_validate(body.payload)
            work = lambda: scenario(parsed, u)
        else:
            if not body.version_id:
                raise ValueError("Recovery needs a version")
            parsed = Recovery.model_validate(body.payload)
            work = lambda: recover(body.version_id, parsed, u)
        return jobs.submit(u["username"], body.kind, body.model_dump(), work)

    @app.get("/api/jobs/{jid}")
    def get_job(jid: str, u=Depends(user)):
        value = jobs.get(jid, u["username"], u["role"] in APPROVE)
        if not value:
            raise HTTPException(404, "Planning job not found")
        return value

    @app.post("/api/jobs/{jid}/cancel")
    def cancel_job(jid: str, u=Depends(user)):
        value = get_job(jid, u)
        if value["status"] != "QUEUED":
            raise Conflict(
                "Only queued jobs can be cancelled; running work finishes as an unapproved proposal"
            )
        with store.connect() as db:
            changed = db.execute(
                "UPDATE solve_jobs SET status='CANCELLED', updated_at=? WHERE id=? AND status='QUEUED'",
                (now(), jid),
            ).rowcount
            if not changed:
                raise Conflict("Job started; it can no longer be cancelled")
            store.audit(db, u["username"], "Cancelled queued solve", {"job": jid})
        return {"ok": True}

    @app.get("/api/versions/{vid}")
    def version(vid: int, u=Depends(user)):
        v = store.version(vid)
        if not v:
            raise HTTPException(404, "Version not found")
        with store.connect() as db:
            v["decisions"] = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM decisions WHERE version_id=? ORDER BY id", (vid,)
                )
            ]
        v["current_comparison"] = compare(
            (store.version() or {}).get("result"), v["result"]
        )
        return v

    class ReviewDecision(Model):
        action: str = Field(pattern="^(REJECTED|SAVED FOR REVIEW)$")
        reason: str = Field(min_length=5, max_length=1000)

    @app.post("/api/versions/{vid}/decision")
    def decision(vid: int, body: ReviewDecision, u=Depends(user)):
        authorize(u, APPROVE if body.action == "REJECTED" else WRITE | {"sales"})
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            v = store.version(vid, db)
            if not v:
                raise HTTPException(404, "Version not found")
            if v["activated_at"]:
                raise Conflict("Published versions are immutable")
            last = db.execute(
                "SELECT action FROM decisions WHERE version_id=? ORDER BY id DESC LIMIT 1",
                (vid,),
            ).fetchone()
            if last and last[0] == "REJECTED":
                raise Conflict("Rejected proposals require a new scenario")
            db.execute(
                "INSERT INTO decisions(version_id,actor,at,action,reason) VALUES (?,?,?,?,?)",
                (vid, u["username"], now(), body.action, body.reason),
            )
            store.audit(
                db, u["username"], body.action, {"version": vid, "reason": body.reason}
            )
        return {"ok": True}

    @app.get("/api/versions/{vid}/report")
    def decision_report(vid: int, u=Depends(user)):
        v = version(vid, u)
        return Response(
            dumps(v),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="decision-v{vid}.json"'
            },
        )

    @app.post("/api/versions/{vid}/activate")
    def activate(vid: int, u=Depends(user)):
        authorize(u, APPROVE)
        return store.activate(vid, u["username"])

    @app.get("/api/orders/{oid}/explain")
    def explanation(oid: str, u=Depends(user)):
        f, rev, v = store.snapshot()
        return (
            {"items": explain(Factory.model_validate(v["inputs"]), v["result"], oid)}
            if v
            else {"items": []}
        )

    @app.get("/api/events")
    def events(u=Depends(user)):
        with store.connect() as db:
            return [
                dict(r, body=json.loads(r["body"]))
                for r in db.execute(
                    "SELECT * FROM events ORDER BY created_at DESC LIMIT 100"
                )
            ]

    @app.get("/api/audit")
    def audit(u=Depends(user)):
        authorize(u, APPROVE | {"management"})
        with store.connect() as db:
            return [
                dict(r)
                for r in db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 200")
            ]

    @app.get("/api/templates/{kind}")
    def download_template(kind: str, u=Depends(user)):
        data = template(kind, store.load())
        return Response(
            data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{kind}.xlsx"'},
        )

    @app.post("/api/imports/{kind}/preview")
    async def import_preview(
        kind: str,
        file: UploadFile = File(...),
        mapping: str = Form(default="{}"),
        u=Depends(user),
    ):
        authorize(u, WRITE)
        if file.content_type not in (
            None,
            "application/octet-stream",
            "text/csv",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ):
            raise ValueError("Unsupported spreadsheet content type")
        content = await file.read(5 * 1024 * 1024 + 1)
        f, rev, v = store.snapshot()
        value = preview(kind, content, file.filename or "", f, json.loads(mapping))
        token = secrets.token_urlsafe(20)
        if value["valid"]:
            with store.connect() as db:
                db.execute(
                    "INSERT INTO imports(id,actor,revision,data,created_at) VALUES (?,?,?,?,?)",
                    (token, u["username"], rev, dumps(value["merged"]), now()),
                )
        value.pop("merged")
        return {**value, "id": token, "revision": rev}

    @app.post("/api/imports/{token}/apply")
    def import_apply(token: str, u=Depends(user)):
        authorize(u, WRITE)
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM imports WHERE id=?", (token,)).fetchone()
            if not row or row["actor"] != u["username"]:
                raise HTTPException(404, "Import preview not found")
            if row["consumed"] or row["revision"] != store.revision(db):
                raise Conflict("Import preview already applied or stale; preview again")
            f = Factory.model_validate_json(row["data"])
            before = store.load(db).model_dump_json()
            store.write_factory(db, f)
            db.execute(
                "INSERT INTO import_backups(import_id,before_data,applied_revision) VALUES (?,?,?)",
                (token, before, store.revision(db)),
            )
            db.execute("UPDATE imports SET consumed=1 WHERE id=?", (token,))
            store.audit(db, u["username"], "Applied validated import", {"id": token})
        return {"ok": True}

    @app.post("/api/imports/{token}/rollback")
    def import_rollback(token: str, u=Depends(user)):
        authorize(u, WRITE)
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT b.*, i.actor FROM import_backups b JOIN imports i ON i.id=b.import_id WHERE b.import_id=?",
                (token,),
            ).fetchone()
            if not row or (row["actor"] != u["username"] and u["role"] not in APPROVE):
                raise HTTPException(404, "Import not found")
            if row["restored"] or row["applied_revision"] != store.revision(db):
                raise Conflict(
                    "Cannot rollback after later edits or schedule activation"
                )
            store.write_factory(db, Factory.model_validate_json(row["before_data"]))
            db.execute(
                "UPDATE import_backups SET restored=1 WHERE import_id=?", (token,)
            )
            store.audit(db, u["username"], "Rolled back import", {"id": token})
        return {"ok": True}

    @app.get("/api/reports/{kind}")
    def report(kind: str, u=Depends(user)):
        f, rev, v = store.snapshot()
        if kind == "factory":
            return Response(
                f.model_dump_json(indent=2),
                media_type="application/json",
                headers={"Content-Disposition": 'attachment; filename="factory.json"'},
            )
        if not v:
            raise ValueError("No approved plan")
        rows = (
            v["result"]["operations"]
            if kind == "operations"
            else (
                v["result"]["orders"]
                if kind == "delivery"
                else v["result"].get("bottlenecks", []) if kind == "capacity" else None
            )
        )
        if rows is None:
            raise HTTPException(404, "Unknown report")
        out = io.StringIO(newline="")
        if rows:
            writer = csv.DictWriter(out, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        k: safe_cell(
                            json.dumps(x) if isinstance(x, (dict, list)) else x
                        )
                        for k, x in row.items()
                    }
                )
        return Response(
            "\ufeff" + out.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{kind}-v{v["id"]}.csv"'
            },
        )

    # Serve the built React app from the same origin as the API.
    dist = Path(__file__).parent.parent / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(dist / "index.html")

    return app


app = create_app()
