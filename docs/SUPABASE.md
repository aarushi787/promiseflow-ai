# Supabase database connection

PromiseFlow's FastAPI backend supports Supabase PostgreSQL. The React app continues to call FastAPI; it receives no database URL, password, service-role key or direct table permissions. Supabase Auth is not enabled by this change: existing PromiseFlow usernames, password hashes, sessions and role checks remain authoritative.

## Login IDs

In the synthetic demo, usernames are `manager`, `planner`, `sales`, `supervisor`, `purchase`, `maintenance`, `management`, and `admin`. All use `promise-demo`. These credentials are for the demo only. Production creates only `admin` using the server's unique `PROMISEFLOW_ADMIN_PASSWORD`; provision named users with `python -m backend.admin USERNAME --role ROLE`.

## Connect an existing Supabase project

1. Open the selected project in Supabase and choose **Connect → Session pooler**. Use the exact host, username and project reference supplied there. The session pooler supports IPv4 connections used by typical persistent backends; direct connections work when the host has IPv6 connectivity. See [Supabase connection documentation](https://supabase.com/docs/guides/database/connecting-to-postgres).
2. Create `.env` in the repository root from `.env.example`. Put the full PostgreSQL connection URL in `PROMISEFLOW_DATABASE_URL`, replacing the password placeholder with the URL-encoded database password. Keep this file private. A Supabase project API URL or publishable/anon key is not a PostgreSQL connection string.
3. Remote connections require `sslmode=verify-full`. The driver uses system certificate roots by default. If the selected endpoint requires Supabase's CA, download it from your project's database connection settings and set `PROMISEFLOW_DB_SSLROOTCERT` to that file's absolute path. Do not disable certificate validation to work around a certificate error.
4. Use a dedicated private schema, default `PROMISEFLOW_DB_SCHEMA=promiseflow`. Reserved Supabase schemas and unsafe identifiers are rejected. The backend creates its own 15 tables, enables RLS and revokes schema/table/sequence grants from PUBLIC and Supabase Data API roles. Keep this schema out of the exposed Data API schemas. See [Supabase RLS documentation](https://supabase.com/docs/guides/database/postgres/row-level-security).
5. Install requirements and run `python -m backend.db_admin check`. This initializes/checks the private schema and prints the database type and revision without credentials. It must say `postgresql`; a `sqlite` result means no cloud URL has been configured.
6. For a new production factory set `PROMISEFLOW_MODE=production`, an exact HTTPS origin, and a unique 16+ character bootstrap admin password before starting the backend. Then import validated production data. Do not copy the demo database into a production factory.
7. Restart FastAPI. `/api/health` performs a database round trip and reports `database: postgresql`. A configured cloud connection failure does not silently fall back to SQLite.

Only put server secrets in the backend environment or `.env`. Do not set a `VITE_` database variable. The existing Docker Compose configuration forwards `PROMISEFLOW_DATABASE_URL` and `PROMISEFLOW_DB_SCHEMA` from the deployment environment; when using a custom CA, mount it read-only and set its container path separately.

## Optional: preserve an existing local factory

Stop the backend to prevent writes during cutover. Make a verified local backup using `python -m backend.backup data/promiseflow.db data/before-supabase.db`. Configure the destination URL and a fresh private schema, then run:

```sh
python -m backend.db_admin migrate --source data/promiseflow.db
```

The importer requires an initialized schema-4 source and an empty destination. It validates the factory, copies master data, schedule versions, users, imports, decisions, audit and execution history in one PostgreSQL transaction, preserves the active plan/revision, verifies row counts and advances identity sequences. It does not modify the local source. Sessions and solve cache are not copied; queued/running jobs become interrupted and must be submitted again. Repeated imports into an initialized destination are rejected without overwriting data.

Keep the same demo/production mode as the source. A migrated demo retains demo passwords and remains explicitly a demo. Restart the backend, sign in again, and verify the active schedule before resuming operations. Retain the local backup until rollout acceptance is complete. PostgreSQL backup/restore should use Supabase backups or `pg_dump`/`pg_restore`; the SQLite backup helper cannot back up PostgreSQL.

## Transaction and operational limits

- The connection adapter keeps bound parameters separate from SQL and uses native PostgreSQL upserts and `RETURNING` IDs. Read snapshots use repeatable-read transactions. Revision-sensitive writes acquire a transaction-scoped advisory lock before reading state, preventing two writers from accepting the same revision.
- Statement and lock timeouts bound database waits. Remote connection errors are sanitized to avoid disclosing URLs/passwords. Database health errors return HTTP 503.
- Use a single backend process/worker as before. Supabase storage does not add a distributed job queue, shared SaaS tenancy, Supabase Auth or multi-worker support. The private schema represents one factory; do not expose one deployment to unrelated organizations as tenants.
- `.env` is loaded without overriding deployment environment variables. Explicit SQLite paths supplied by tests or local tools override the cloud URL, so local tests do not mutate a configured Supabase factory.

## Testing

The normal regression suite continues to use temporary SQLite databases. `tests/test_database.py` adds URL/TLS/schema/parameter validation. The GitHub Actions workflow also runs a disposable PostgreSQL 17 service and exercises generated IDs, rollback, private-schema privileges, concurrent revision checks, migration and the API/execution/decision tests against PostgreSQL. `PROMISEFLOW_TEST_POSTGRES_URL` accepts only a local disposable server; each test creates and removes its own randomly named schema. Never use a production connection for integration tests.

Project connection and real Supabase smoke tests require the chosen project's credentials. Passing local or CI tests does not mean a particular Supabase project has been connected.
