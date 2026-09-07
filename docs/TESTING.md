# Verification

Run `npm test`, `npm run build`, and `npm run lint` from the root. Tests use isolated temporary databases and synthetic inputs, never the active user's database. Run `python -m backend.benchmark` for the repeatable synthetic scope benchmark.

The baseline had 43 passing tests. V3 adds quality/order hold, breaks, subminute recovery, duplicate requirements, hard deadlines, old due dates, complete impact traversal, forged schedule rejection, reverse environment-mode protection, formula export defense, cache invalidation, freshness, overtime accounting, extended template roundtrips, column mapping, rollback, terminal rejection and background-job authorization/completion coverage.

Manufacturing validation is independent of the solver model construction. A green test suite does not establish that a particular factory's standards, skills, fixture inventory, material reservations or vendor times are correct. Pilot acceptance must reconcile a real representative week.

The installed Starlette/httpx test adapter emits two dependency deprecation warnings. Do not suppress unexpected failures. Frontend production build and lint are required after UI edits. Browser acceptance covers promise, readiness, scenario impact, versions, imports and responsive layout; local verification results and any untested surfaces belong in V3_IMPLEMENTATION_REPORT.

## V3.2 database verification — 7 September 2026

Local verification: 98 tests passed; four PostgreSQL integration cases were skipped because no disposable local PostgreSQL server was configured. Frontend lint and production build passed. GitHub Actions then passed the PostgreSQL integration, API, execution and decision tests using PostgreSQL 17 for commit `6eedb81`: [verification run](https://github.com/aarushi787/promiseflow-ai/actions/runs/34091118293). This verifies the database adapter; a live Supabase project connection remains dependent on project credentials. The local application health check reports SQLite, with active schedule 1 and revision 2 preserved.
