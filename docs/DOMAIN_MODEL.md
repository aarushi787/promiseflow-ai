# Canonical factory model

The UI, spreadsheets and API normalize into `Factory` in `backend/models.py`. A factory contains customers, products, linear routings, approved resource alternatives, resources, materials, calendars, suppliers, tools/operator pools, orders and planning settings. Product quantities create transfer-batch jobs; each job traverses the routing. Resource type is descriptive; eligibility is explicit.

Requested and committed delivery are soft due dates. Optional `hard_deadline` is a hard completion constraint. `ON HOLD` retains the customer commitment but blocks production. Material `quality_hold` prevents consumption regardless of its ETA; clearing the hold requires an authorized, audited master edit based on a real quality release. This MVP does not implement a separate quality-signature role.

Each SQLite deployment represents one company and one plant. Nested JSON entities are validated as an aggregate, not presented as a fully normalized relational ERP schema. Schedule versions contain complete input snapshots. Decisions reference versions; solve jobs record actor and request; import backups contain pre-import masters. No shared-database tenant selector exists. Separate deployments, databases, origins and credentials are required for separate companies.

Future organization/facility IDs must be enforced throughout the persistence and authorization layers before enabling shared SaaS tenancy. Do not add UI-only tenant filtering. Actual production, multi-lot reservations, approved alternate routes and rework require new canonical entities and independent scheduling validation.
