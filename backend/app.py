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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
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
from .database import DatabaseUnavailable
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
# Serverless instances can be frozen after responding, so planning runs inline.
SERVERLESS = bool(os.environ.get("VERCEL"))
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


def create_app(db_path=None, *, db_schema=None):
    store = Store(db_path, schema=db_schema)
    jobs = Jobs(store, inline=SERVERLESS)

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
                "INSERT INTO meta VALUES ('mode',?) ON CONFLICT (key) DO NOTHING",
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
            # Concurrent serverless instances share the database, so a cold start
            # only reclaims jobs that have outlived any possible request.
            cutoff = (
                (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
                if SERVERLESS
                else "9999"
            )
            db.execute(
                "UPDATE solve_jobs SET status='INTERRUPTED', error='Service restarted; submit again', updated_at=? WHERE status IN ('QUEUED','RUNNING') AND updated_at < ?",
                (now(), cutoff),
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

    app = FastAPI(title="ProductionSaathi", version="3.2.0", lifespan=lifespan)
    app.state.store = store

    @app.middleware("http")
    async def security(request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            allowed = [
                origin.strip()
                for origin in os.environ.get(
                    "PROMISEFLOW_ORIGINS",
                    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8017,http://127.0.0.1:8017,https://productionsaathi.vercel.app,https://promise-flow-ai.vercel.app",
                ).split(",")
                if origin.strip()
            ]
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

    @app.exception_handler(DatabaseUnavailable)
    async def unavailable(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

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
        with store.connect() as db:
            db.execute("SELECT 1").fetchone()
        return {
            "status": "ok",
            "demo": DEMO,
            "version": "3.2.0",
            "database": "postgresql" if store.database.postgres else "sqlite",
        }

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

    @app.get("/api/maintenance/reminders")
    def maintenance_reminders(u=Depends(user)):
        f, rev, active = store.snapshot()
        now_dt = datetime.now()
        reminders = []
        counts = {"OVERDUE": 0, "DUE_SOON": 0, "MAINTENANCE": 0, "HEALTHY": 0}

        for r in f.resources:
            hours_since = float(getattr(r, "working_hours_since_service", 0.0) or 0.0)
            max_hours = float(getattr(r, "max_working_hours", 200.0) or 200.0)
            hours_ratio = min(1.0, hours_since / max_hours) if max_hours > 0 else 0.0

            prod_since = int(getattr(r, "production_count_since_service", 0) or 0)
            max_prod = int(getattr(r, "max_production_count", 5000) or 5000)
            prod_ratio = min(1.0, prod_since / max_prod) if max_prod > 0 else 0.0

            last_date_str = getattr(r, "last_service_date", None)
            days_since = 0
            if last_date_str:
                try:
                    days_since = max(0, (now_dt - datetime.fromisoformat(last_date_str)).days)
                except Exception:
                    days_since = 0
            interval_days = int(getattr(r, "service_interval_days", 30) or 30)
            calendar_ratio = min(1.0, days_since / interval_days) if interval_days > 0 else 0.0

            health_status = "HEALTHY"
            if r.status == "MAINTENANCE":
                health_status = "MAINTENANCE"
            elif r.status == "BREAKDOWN":
                health_status = "OVERDUE"
            elif hours_since >= max_hours or prod_since >= max_prod or (last_date_str and days_since >= interval_days):
                health_status = "OVERDUE"
            elif hours_ratio >= 0.85 or prod_ratio >= 0.85 or calendar_ratio >= 0.85:
                health_status = "DUE_SOON"

            counts[health_status] = counts.get(health_status, 0) + 1

            reminders.append({
                "resource_id": r.id,
                "resource_name": r.name,
                "department": r.department,
                "resource_type": r.type,
                "status": r.status,
                "health_status": health_status,
                "working_hours_since_service": round(hours_since, 1),
                "total_working_hours": round(float(getattr(r, "total_working_hours", 0.0) or 0.0), 1),
                "max_working_hours": max_hours,
                "hours_ratio": round(hours_ratio * 100, 1),
                "production_count_since_service": prod_since,
                "total_production_count": int(getattr(r, "total_production_count", 0) or 0),
                "max_production_count": max_prod,
                "prod_ratio": round(prod_ratio * 100, 1),
                "last_service_date": last_date_str,
                "days_since_service": days_since,
                "service_interval_days": interval_days,
                "calendar_ratio": round(calendar_ratio * 100, 1),
                "maintenance_workflow_mode": getattr(r, "maintenance_workflow_mode", "HYBRID"),
                "custom_workflow_rule": getattr(r, "custom_workflow_rule", "") or "",
                "maintenance_notes": getattr(r, "maintenance_notes", "") or "",
                "unavailable_windows": [w.model_dump() for w in r.unavailable],
            })

        return {
            "reminders": reminders,
            "counts": counts,
            "timestamp": now_dt.isoformat(),
        }

    class MaintenanceLog(Model):
        resource_id: str
        notes: str = ""

    @app.post("/api/maintenance/log-service")
    def log_maintenance_service(body: MaintenanceLog, u=Depends(user)):
        authorize(u, WRITE | {"maintenance", "supervisor"})
        f, rev, _ = store.snapshot()
        idx = next((i for i, r in enumerate(f.resources) if r.id == body.resource_id), None)
        if idx is None:
            raise HTTPException(404, f"Resource {body.resource_id} not found")
        
        r = f.resources[idx].model_dump()
        r["working_hours_since_service"] = 0.0
        r["production_count_since_service"] = 0
        r["last_service_date"] = datetime.now().isoformat().split("T")[0]
        if body.notes:
            r["maintenance_notes"] = body.notes
        if r["status"] == "MAINTENANCE":
            r["status"] = "AVAILABLE"
            
        f.resources[idx] = type(f.resources[idx]).model_validate(r)
        store.save_factory(
            f, rev, u["username"], f"Logged maintenance service for machine {body.resource_id}"
        )
        return {"ok": True, "resource_id": body.resource_id, "status": f.resources[idx].status}

    class MaintenanceConfig(Model):
        resource_id: str
        max_working_hours: float = Field(default=200.0, ge=1)
        max_production_count: int = Field(default=5000, ge=1)
        service_interval_days: int = Field(default=30, ge=1)
        maintenance_workflow_mode: Literal[
            "HOURS", "PRODUCTION_COUNT", "CALENDAR", "CUSTOM", "HYBRID"
        ] = "HYBRID"
        custom_workflow_rule: str = ""
        maintenance_notes: str = ""

    @app.post("/api/maintenance/config")
    def update_maintenance_config(body: MaintenanceConfig, u=Depends(user)):
        authorize(u, WRITE | {"maintenance"})
        f, rev, _ = store.snapshot()
        idx = next((i for i, r in enumerate(f.resources) if r.id == body.resource_id), None)
        if idx is None:
            raise HTTPException(404, f"Resource {body.resource_id} not found")
        
        r = f.resources[idx].model_dump()
        r["max_working_hours"] = body.max_working_hours
        r["max_production_count"] = body.max_production_count
        r["service_interval_days"] = body.service_interval_days
        r["maintenance_workflow_mode"] = body.maintenance_workflow_mode
        r["custom_workflow_rule"] = body.custom_workflow_rule
        r["maintenance_notes"] = body.maintenance_notes
        
        f.resources[idx] = type(f.resources[idx]).model_validate(r)
        store.save_factory(
            f, rev, u["username"], f"Updated maintenance workflow rules for machine {body.resource_id}"
        )
        return {"ok": True, "resource_id": body.resource_id}

    class MaintenanceDowntime(Model):
        resource_id: str
        start: str
        end: str
        reason: str = "Preventive Maintenance"

    @app.post("/api/maintenance/schedule-downtime")
    def schedule_maintenance_downtime(body: MaintenanceDowntime, u=Depends(user)):
        authorize(u, WRITE | {"maintenance", "supervisor"})
        f, rev, _ = store.snapshot()
        idx = next((i for i, r in enumerate(f.resources) if r.id == body.resource_id), None)
        if idx is None:
            raise HTTPException(404, f"Resource {body.resource_id} not found")
        
        r = f.resources[idx].model_dump()
        r["unavailable"].append({
            "start": body.start,
            "end": body.end,
            "reason": body.reason,
        })
        r["status"] = "MAINTENANCE"
        f.resources[idx] = type(f.resources[idx]).model_validate(r)
        store.save_factory(
            f, rev, u["username"], f"Scheduled maintenance downtime for machine {body.resource_id}"
        )
        return {"ok": True, "resource_id": body.resource_id}


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

    @app.get("/api/reports/export-all.xlsx")
    def report_export_all(u=Depends(user)):
        f, rev, v = store.snapshot()
        wb = openpyxl.Workbook()
        # Remove default sheet
        default_sheet = wb.active
        
        # Sheet 1: Orders
        ws_orders = wb.create_sheet(title="Orders")
        ws_orders.append(["Order ID", "Customer ID", "Product ID", "Quantity", "Order Date", "Requested Date", "Priority", "Status"])
        for o in f.orders:
            ws_orders.append([o.id, o.customer_id, o.product_id, o.quantity, o.order_date, o.requested_date, o.priority, o.status])
            
        # Sheet 2: Materials
        ws_mat = wb.create_sheet(title="Materials")
        ws_mat.append(["Material ID", "Description", "Stock", "Reserved", "Safety Stock", "Available", "Incoming", "Arrival Date", "Supplier"])
        for m in f.materials:
            avail = max(0, m.stock - m.reserved - m.safety_stock)
            ws_mat.append([m.id, m.description, m.stock, m.reserved, m.safety_stock, avail, m.incoming, m.arrival or "", m.supplier_id or ""])
            
        # Sheet 3: Resources
        ws_res = wb.create_sheet(title="Resources")
        ws_res.append(["Resource ID", "Name", "Type", "Department", "Capacity", "Efficiency", "Cost/hr", "Calendar ID"])
        for r in f.resources:
            ws_res.append([r.id, r.name, r.type, r.department, r.capacity, r.efficiency, r.cost_per_hour, r.calendar_id])
            
        # Sheet 4: Products
        ws_prod = wb.create_sheet(title="Products")
        ws_prod.append(["Product ID", "Name", "Routing ID", "Batch Size", "Lead Time Days"])
        for p in f.products:
            ws_prod.append([p.id, p.name, p.routing_id, p.batch_size, p.lead_time_days])
            
        if default_sheet in wb.worksheets:
            wb.remove(default_sheet)
            
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return Response(
            buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="factory_master_data.xlsx"'},
        )

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
            
        if kind == "material-shortage":
            # Identify materials that will run out or are below safety stock within active plan
            shortage_rows = []
            for m in f.materials:
                avail = m.stock - m.reserved - m.safety_stock
                status = "CRITICAL SHORTAGE" if avail < 0 else "LOW BUFFER" if avail <= m.safety_stock else "OK"
                if avail <= 0 or status != "OK":
                    shortage_rows.append({
                        "material_id": m.id,
                        "description": m.description,
                        "current_stock": m.stock,
                        "allocated_reserved": m.reserved,
                        "safety_stock": m.safety_stock,
                        "net_shortage": abs(avail) if avail < 0 else 0,
                        "incoming_replenishment": m.incoming,
                        "expected_arrival": m.arrival or "No PO Arrival Scheduled",
                        "supplier_id": m.supplier_id or "—",
                        "urgency": status,
                    })
            if not shortage_rows:
                shortage_rows.append({
                    "material_id": "ALL_OK",
                    "description": "No material shortages detected for active scheduled orders",
                    "current_stock": "—",
                    "allocated_reserved": "—",
                    "safety_stock": "—",
                    "net_shortage": 0,
                    "incoming_replenishment": "—",
                    "expected_arrival": "—",
                    "supplier_id": "—",
                    "urgency": "HEALTHY",
                })
            rows = shortage_rows

        elif kind == "job-cards":
            # Shift-wise printable machine job cards
            ops = v["result"]["operations"]
            job_rows = []
            for op in sorted(ops, key=lambda x: (x.get("resource_id", ""), x.get("start", ""))):
                job_rows.append({
                    "machine_resource": op.get("resource_id"),
                    "scheduled_start": op.get("start", "").replace("T", " ")[:16],
                    "scheduled_finish": op.get("end", "").replace("T", " ")[:16],
                    "order_no": op.get("order_id"),
                    "batch_no": op.get("batch_id"),
                    "operation_step": op.get("operation_name") or op.get("operation_id"),
                    "assigned_operator": op.get("operator_id") or "Line Operator",
                    "tooling_fixture": op.get("tool_id") or "Standard Tooling",
                    "status": op.get("status", "SCHEDULED"),
                })
            rows = job_rows

        elif kind == "operations":
            rows = v["result"]["operations"]
        elif kind == "delivery":
            rows = v["result"]["orders"]
        elif kind == "capacity":
            rows = v["result"].get("bottlenecks", [])
        else:
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
