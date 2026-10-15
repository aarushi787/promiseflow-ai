# Vercel build configuration

## Startup database errors

`DatabaseUnavailable` while importing `backend/app.py` means the function could not open its configured database, not that a favicon is missing. Connection diagnostics now distinguish `DB_AUTH`, `DB_TLS`, `DB_DNS`, and `DB_NETWORK` without including driver text or credentials.

For the MCCIA deployment, verify these server environment settings and redeploy after saving:

- `PROMISEFLOW_DATABASE_URL`: the chosen Supabase project's **session pooler** PostgreSQL URI, including its correct database password and `sslmode=verify-full`. A public API key cannot substitute for this URI.
- `PROMISEFLOW_DB_SSLROOTCERT=backend/certs/supabase-ca.crt`. Relative certificate paths resolve against the application root. If this variable is absent, Supabase endpoints use the bundled CA automatically. An explicitly configured missing file is rejected, not silently ignored.
- `PROMISEFLOW_MODE=demo` for the previously migrated synthetic factory. Use a separate database/schema for production.
- `PROMISEFLOW_ORIGINS=https://productionsaathi.vercel.app,https://promise-flow-ai.vercel.app` for the production / demo domains.

Git pushes transfer source code, not the old Vercel project's environment variables. Do not upload `.env` to GitHub. A successful redeployment must be followed by a PostgreSQL `/api/health` response and an actual login check.

The repository-root `pyproject.toml` declares `backend.app:app` as the FastAPI entrypoint and builds the React frontend into `frontend/dist`. FastAPI serves the interface and `/api` on the same origin. Keep the Vercel Root Directory at the repository root and select the FastAPI framework. Remove stale Build Command or Output Directory overrides; dashboard build commands override the repository script.

This fixes entrypoint discovery, not every deployment/runtime requirement. Follow the [official FastAPI guide](https://vercel.com/docs/frameworks/backend/fastapi).

## Server configuration

Local `.env` files are deliberately not published. Configure the server-only `PROMISEFLOW_DATABASE_URL` in the deployment environment using the Supabase session pooler and `sslmode=verify-full`. The public Supabase API URL and publishable key cannot replace it. Configure a trusted CA certificate accessible inside the deployment if required; a Windows path in `PROMISEFLOW_DB_SSLROOTCERT` will not work on Vercel. Never disable TLS verification.

Set `PROMISEFLOW_MODE` to match the database. The migrated sample database is **demo**, not production. Production requires a separate database/schema, a unique `PROMISEFLOW_ADMIN_PASSWORD` of at least 16 characters and exact HTTPS `PROMISEFLOW_ORIGINS`. Keep a demo deployment access-protected because its credentials are published. Do not put database secrets in `NEXT_PUBLIC_` or `VITE_` variables.

## Runtime boundary

On Vercel (detected through the `VERCEL` environment variable) planning jobs run **inside the submitting request** instead of a background thread, because a function instance can be frozen as soon as it responds. `POST /api/jobs` still returns 202 with the job id, but the job is already `COMPLETED` or `FAILED`; the interface's polling picks it up on the first check. The solver's search budget (0.3 deterministic seconds, 30 s wall cap) fits within the function `maxDuration` of 60 s set in `vercel.json`.

- A cold start only marks jobs `INTERRUPTED` when they are more than 10 minutes old, so a new instance cannot cancel another instance's running request.
- SQLite is refused on Vercel; `PROMISEFLOW_DATABASE_URL` must point at PostgreSQL (Supabase).
- Login rate limits and the "one solve at a time" lock are per instance. Concurrent solves on different instances are safe because activation checks data revisions, but heavy simultaneous use is better served by the Docker deployment with one worker.

After deployment, verify `/api/health` reports PostgreSQL, login returns JSON, the saved active plan is present, and the supported worker can complete and publish a sandbox scenario. A frontend-only page is not a working backend deployment.
