# PromiseFlow AI V3 — implementation report

Verified 6 September 2026. This release improves the existing application into a decision-oriented pilot MVP. It does not claim all 183 roadmap sections or unattended plant readiness.

## 1. Existing-system audit

Inspected application source, tests, documentation, dependencies/configuration, deployment files and the supplied continuation. The directory has no Git repository/history. Baseline: React/TypeScript/Vite, FastAPI/Pydantic, SQLite aggregate entities and immutable schedule snapshots, OR-Tools CP-SAT, five spreadsheet templates, synchronous scenarios and 43 passing tests. No LLM generated schedules. See V3_AUDIT for the findings recorded before implementation.

## 2. Problems by priority

P0 findings fixed: reverse demo/production mode exposure, auto-expiring material hold, disappearing on-hold commitments, overtime erasing shift breaks, duplicate material/capability ambiguity, subminute premature availability, incomplete worsening-impact counts, inconsistent operation/delivery validation and spreadsheet formula/structure weaknesses.

P1 work delivered: readiness/freshness/assumptions, solver metadata, persistent cache, background request statuses, realistic incremental overtime calculation, hard deadlines, decision review/rejection, expanded onboarding/mapping/rollback. P1 release gates still open: actual-progress reconciliation, formal quality/engineering approvals, richer material allocation, strict objective hierarchy and rolling-horizon stability. P2/P3 are ranked in ROADMAP; they were not disguised as completed features.

## 3. Architecture before and after

Before: UI → synchronous API → validated factory → copied scenario → CP-SAT → version → validator → activation → reports.

After: UI → authenticated job submission → persisted bounded worker → canonical input + readiness → fingerprint/cache → CP-SAT → deterministic cost/impact/evidence → immutable proposal → save/reject/approve decision gate → independent validation → active pointer. Spreadsheet previews now retain rollback snapshots. `intelligence.py`, `cache.py`, `jobs.py`, `benchmark.py` and `backup.py` isolate added responsibilities. The working frontend/backend stack was preserved.

## 4. Exact implemented features

- Promise Checker default view for Sales/PPC/manager/admin; other roles retain dashboard access.
- Readiness checks, explicit omissions/default assumptions, data-source confirmation and stale/past-epoch warnings; incomplete confidence prevents an unconditional feasible promise label.
- Indefinite material holds, visible blocked order holds, hard deadlines and conservative minute rounding.
- Complete prior-commitment comparison, including removal, risk escalation and further lateness.
- Solver/version/settings/bound/time evidence and cached-result provenance.
- Persisted background requests; creator/manager visibility; bounded queue; API cancellation for queued jobs; interrupted status after restart.
- Three recovery comparisons through existing workflow, now with same-workload incremental costs and correctly measured overtime premiums.
- Saved review notes, terminal rejection, approval audit records, historical/current comparisons and decision JSON export.
- Resource-by-day heatmap and expandable material → products → open orders → customers view.
- Customers, Products, Suppliers, Operators, Tools and Maintenance templates added to existing imports; Resources alias, optional header mapping, stricter spreadsheet validation, atomic apply and revision-safe undo.
- Online backup/integrity verification and a private non-root Docker Compose configuration.

## 5. Solver implementation

OR-Tools CP-SAT remains authoritative. Optional intervals choose approved resource/operator assignments; cumulative constraints enforce shared capacity. Fixed promise work protects existing assignments. Independent validation reconstructs quantities, identities, material availability, calendars, precedence, deadlines and delivery classification. Fixed seed 42, one worker, 0.3 deterministic budget and 30-second solver wall cap are disclosed. FEASIBLE is never labeled OPTIMAL. See OPTIMIZATION_ENGINE and CONSTRAINTS for manufacturing assumptions.

## 6. Domains supported and deferred

Current: finite production planning, sales promise checks, load/capacity visibility, configured operator/tool constraints, material/supplier impact, maintenance/breakdown simulation and qualified external processing. Automotive synthetic configuration remains the supplied demo.

Deferred: actual execution/rework, advanced workforce planning, alternate manufacturing routes/materials, strict changeover/cleaning, pack installation, multi-plant, CAPEX, energy and ML. No predicted probability or ROI is fabricated.

## 7. Security improvements

Both environment-mode mismatch directions fail closed. New job endpoints enforce backend roles and request ownership. Rejected/stale/blocked proposals cannot publish. Import rollback cannot overwrite subsequent edits. Spreadsheet macros, external links, formulas, unsafe exports, unexpected sheets and extra undeclared row values are rejected or escaped. Existing password/session/origin/RBAC protections remain. Shared SaaS tenancy is **not** implemented; each company requires a separate deployment/database. See SECURITY for deployment acceptance requirements.

## 8. Test results

Final full suite: **75 passed**, with two known dependency deprecation warnings, in 64.47 seconds. Production TypeScript/Vite build and frontend lint passed. Compiled JS: 361.60 KB / 102.16 KB gzip; CSS: 27.72 KB / 7.09 KB gzip.

Browser verification exercised new-order background checking, all three recovery options, review recording, resource heatmap interaction and expanded Imports. Desktop at 1440 × 1000 and mobile at 390 × 844 were visually inspected; temporary viewport overrides were reset. API tests cover approval/rejection and import rollback using temporary databases. Backup/restore-content verification passed. The active demo plan remained v1; browser-generated proposals v5–v8 stayed unapproved.

## 9. Performance benchmarks

50 orders / 200 operations / 10 resources: FEASIBLE, independently validated, 2.785 seconds end-to-end. 500 / 2,500 / 50 and 2,000 / 10,000 / 150 were rejected by the 1,200-operation guard in 0.004 and 0.020 seconds; those are not optimization performance claims. See PERFORMANCE and machine-readable benchmark-results.json. Large Gantt stress/virtualization remains unvalidated.

## 10. Demo instructions

Open the running local app, sign in as Production manager with demo password `promise-demo`, inspect readiness and use a unique new order number. Compare reoptimization, overtime and material-expedite alternatives; examine every existing commitment before reviewing a proposal. Simulate breakdowns from Disruptions and inspect Bottlenecks. Detailed walkthrough: DEMO_GUIDE. No customer notification or schedule publication occurs automatically.

## 11. Remaining limitations

Single-company SQLite installation, one API process, no actuals reconciliation, no inventory ledger, linear routes, one incoming material lot, fixed setup, one-unit pool demand, no shared SaaS isolation, no SSO/MFA, no automated running-job cancellation, no PDF decision export and no formal quality signature workflow. Docker and production HTTPS were not run because Docker is unavailable on this host. Real plant calibration and deployment/security acceptance remain necessary. KNOWN_LIMITATIONS is the release boundary.

## 12. Ranked next improvements

1. Actual-progress reconciliation and safe rolling/frozen horizons.
2. Formal engineering/quality approvals, richer material reservations and supplied scenario quotes.
3. On-premise HTTPS/security/restore acceptance, monitoring and worker recovery.
4. Strict objective hierarchy, schedule stability and operation-level overrides.
5. Guided spreadsheet onboarding, per-cell lineage, printable reports and validated fabrication configuration.
6. Scale/virtualization and PostgreSQL/shared-tenancy architecture when required.
7. CAPEX, energy and real-data ML only after core reliability and sufficient evidence.

Documentation supplied: README, ARCHITECTURE, DOMAIN_MODEL, OPTIMIZATION_ENGINE, CONSTRAINTS, DATA_IMPORT, SCENARIO_ENGINE, SECURITY, DEPLOYMENT, ON_PREMISE, TESTING, PERFORMANCE, DEMO_GUIDE, PILOT_GUIDE, INDUSTRY_PACKS, ROADMAP and KNOWN_LIMITATIONS.
