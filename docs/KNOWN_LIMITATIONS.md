# Known limitations and release gates

This is a tested, production-oriented **pilot MVP**, not a plant-certified autonomous planning service. The V3 request is intentionally phased; many advanced sections are not implemented.

- Single company/plant/database and one API process. SQLite and private PostgreSQL are supported. No shared-tenancy isolation, SSO/MFA or application HA.
- V3.1 adds manual actual-production events and whole-order reconciliation. Partial quantities are visible but cannot yet be optimized: planning and master replacement pause while observed orders remain unreconciled. All their batch operations must finish, and a manager must confirm current material balances, before replanning. No rework, scrap, lot consumption ledger, historical event correction/backfill or continuous live-clock reconciliation. The enforced time boundary advances on reconciliation only. See EXECUTION.md.
- Linear routes and fixed setup per batch; no sequence-dependent cleaning, alternate routes, multiple simultaneous operator demand, vessel co-batching or approved substitute materials.
- One incoming material lot; conservative full-order preallocation; no partial customer shipment. Generic resource pools consume one unit per operation.
- Weighted objectives rather than strict hierarchy; limited schedule stability; 1,200 operations maximum. Bigger requested benchmarks are rejected, not optimized.
- Running solves are not interruptible from the UI. Queued cancellation is API-only. Restarted jobs require retry. Multi-process execution is unsupported.
- Costs omit unconfigured charges. Aggregate source/freshness is user-confirmed, not per-cell automated lineage. No confidence probability or predictive model.
- XLSX/CSV mapping is an advanced JSON field; Maintenance IDs are import-row identifiers; rollback is allowed only without subsequent changes.
- Decision exports are JSON plus approved CSV reports, not PDF/Excel decision packs. No optional LLM copilot is enabled.
- Formal quality-role signatures, alternate supplier/material approval and changeover rules remain pilot scope exclusions. A hold cannot automatically expire.
- Docker/HTTPS deployment and real factory accuracy need target-environment validation. Frontend large-scale and broader accessibility testing remain rollout tasks.

See ROADMAP for ranked next work; do not market deferred features as implemented.
