# Deployment and operations

V3 adds `compose.yaml`, an online backup command and persisted background planning statuses. Read [ON_PREMISE](ON_PREMISE.md) for current setup and restore instructions. Both directions of demo/production mode mismatch are rejected. The former no-background-queue limitation below is superseded by a bounded single-process worker, not a distributed queue. Schema additions are idempotent at version 4. V3.2 adds private PostgreSQL storage; see [Supabase setup](SUPABASE.md).

## Local evaluation

Use the README setup steps and `start.ps1`. Bind to 127.0.0.1. The sample factory, orders, stock, customers and suppliers are synthetic; timestamps are relative to first initialization. The approved plan has a fixed planning epoch for reproducible demonstrations.

The backend loads the repository-root `.env` without overriding existing deployment environment variables. Use `.env.example` as a template; keep credentials out of source control.

## Production-mode pilot

1. Use a new persistent database path. Demo databases are explicitly rejected in production mode.
2. Set `PROMISEFLOW_MODE=production`, `PROMISEFLOW_DB` (SQLite) or `PROMISEFLOW_DATABASE_URL` (PostgreSQL), and a unique `PROMISEFLOW_ADMIN_PASSWORD` of at least 16 characters before the first start.
3. Terminate HTTPS at a reverse proxy. Set `PROMISEFLOW_ORIGINS` to exact comma-separated HTTPS origins. Secure session cookies will not work over plain HTTP in production.
4. Run one Python service worker. Keep the service private to the plant network or an authenticated network boundary. Apply a reverse-proxy upload/request limit, request timeout suitable for optimization, and rate limits.
5. Production initializes an empty factory and one admin account. Sign in with username `admin`. Set up calendars, customers, suppliers, qualified resources, routings, products, materials and orders in that dependency order. Templates contain examples only when corresponding records exist.
6. Provision named users from a trusted terminal: `python -m backend.admin aarushi --role manager`. The password is entered interactively and never put in command history. User creation does not overwrite existing accounts.
7. Generate and validate a proposed plan. Review actual job/material/shift assumptions with PPC before approving a live schedule.

The included Dockerfile builds the frontend and Python service, runs as a non-root user and provides a health check. It defaults to production mode, so it requires the environment above. Map the private service port 8017 behind your HTTPS proxy and mount a persistent, correctly owned `/app/data` volume. The image has not been built on this Windows host; local build/test verification covers the application itself.

## Operational checks

- Back up SQLite with its online backup API, not by copying only the live main database file while WAL is active. Store backups encrypted according to plant policy. Test restoring a backup into an isolated instance.
- Keep the database and environment secrets off source control; `.gitignore` and `.dockerignore` exclude them.
- Monitor `/api/health`, request error rate, solver statuses, queue/busy responses, disk space and backup age. A healthy HTTP process does not certify factory-data accuracy.
- Pin dependency versions through `requirements.txt` and `frontend/package-lock.json`. Run tests before dependency upgrades. Record the solver version when comparing reproduced schedules.
- Build the frontend before launching the single-server deployment. Static assets are discovered at startup; restart after a new build.
- Schema initialization is idempotent at version 4. Future schema migrations must be explicit and backed up; there is no full migration framework yet.

## Acceptance gate before real customer promises

Validate cycle/setup times and units, resource capability, operator/tool capacity, material reservation ownership, safety stocks, vendor calendars and transit, holidays, batch sizes, the planning epoch, frozen work, delivery cutoffs, customer priority weights and risk buffer. Reconcile a representative week against the planner’s known achievable schedule. Exercise breakdown and shortage cases and verify no approved commitment disappears. This application currently requires manual master/status updates; it is not connected to live ERP, PLC or shop-floor events.

## Current deployment boundaries

One plant and one timezone per database, one API worker, SQLite or private PostgreSQL persistence. No SSO/MFA, tenant isolation, application HA/failover, distributed job queue, password-recovery UI or external notifications. These are rollout requirements to assess, not capabilities claimed by this MVP. Sites/Cloudflare Workers cannot host the Python CP-SAT dependency; use a compatible Python server/container.
