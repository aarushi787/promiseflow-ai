# On-premise installation

Use Python 3.12 and Node 24 to follow README local setup. The compiled UI and FastAPI API run together. No LLM key or cloud account is needed. Production mode requires HTTPS because session cookies are Secure.

`compose.yaml` builds the included non-root image, persists `/app/data`, exposes only loopback port 8017, drops Linux capabilities and disables privilege escalation. Set `PROMISEFLOW_ADMIN_PASSWORD` and exact HTTPS `PROMISEFLOW_ORIGINS` before `docker compose up --build -d`. Configure the plant HTTPS reverse proxy, request limits, logs and firewall separately. Docker was not available for runtime validation in this Windows verification; validate the image and volume ownership on the target server.

One API worker and one process per database are required. The worker pool executes one solve at a time with at most four pending/running jobs. Do not run multiple application processes against the same database: startup marks abandoned jobs interrupted and the solver lock is local.

Backup: `python -m backend.backup data/promiseflow.db backups/NEW-NAME.db`. Create the backups directory first. The command uses SQLite online backup and integrity checking and refuses an existing destination. Encrypt and restrict backup storage. Restore offline to a **new** database path, inspect integrity, preserve the production mode, then point a stopped isolated instance to the restored path. Never copy only the live main DB while WAL writes continue.

Schema version 3 adds idempotent tables and model fields with defaults. Back up before upgrade. There is no automated downgrade or PostgreSQL migration; test restore rather than guessing compatibility. Keep old releases and their corresponding backups together.
