# Security and isolation

The supported deployment is a private, single-company installation. **No shared-tenant SaaS isolation is implemented.** MCCIA companies require separate databases, origins, processes and credentials. Do not expose one installation as a multi-company service.

Passwords use salted PBKDF2-SHA256 (310,000 rounds), random session tokens stored only as hashes, eight-hour expiry, HttpOnly/SameSite Strict cookies, and Secure cookies in production. Backend role checks restrict master writes, solves and manager/admin publication. Sales cannot publish, including through the background-job endpoint. Jobs are readable by their creator or manager/admin; cross-role job IDs are not sufficient authorization.

Startup rejects demo/production database mismatch in both directions. Production initializes only admin and requires a bootstrap secret of at least 16 characters. Demo secrets are confined to demo installations. Provision named users locally using `python -m backend.admin NAME --role ROLE`.

Parameterized SQLite queries, aggregate validation, atomic revisions, independently validated activation, origin checks, CSP, frame denial and non-cacheable API responses protect current boundaries. Upload limits and spreadsheet formula defenses are described in DATA_IMPORT. The result cache is local to the company database. Raw production data is not sent to an LLM or external analytics service.

Still required before broader rollout: security penetration testing, SSO/MFA, password reset/revocation UI, distributed rate limits, proxy request-body limits and timeout enforcement, operational log/retention policy, encrypted disks/backups and restore drills. Current login throttling and worker queue are per process. A global aggregate PUT is deliberately limited to planners/managers/admins; field-level purchase/quality approval is not yet implemented.
