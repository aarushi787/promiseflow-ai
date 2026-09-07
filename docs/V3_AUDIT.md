# V3 audit — 6 September 2026

## Inspected baseline

React/TypeScript/Vite → FastAPI session/RBAC → Pydantic aggregate validation → SQLite JSON entities → copied scenario inputs → CP-SAT optional intervals and cumulative capacity → saved proposal → independent validator → manager activation → Gantt/CSV reports. No LLM, ERP adapter, execution ingestion, queue or tenant router exists. No Git history is available: this directory is not a Git repository. Source, tests, configuration, documentation and the supplied continuation were inspected before implementation; generated dependency/build directories are not application source.

## Priorities before modification

| Priority | Finding | Required response |
|---|---|---|
| P0 | A production database can be opened in demo mode and receive demo accounts | Reject mode mismatch in both directions |
| P0 | Material quality hold becomes incoming inventory and automatically expires | Explicit indefinite hold; retain inventory and safety stock; require authorized master correction |
| P0 | ON HOLD orders disappear from commitment results | Retain as blocked; prevent incomplete publication |
| P0 | Overtime combines split shifts and erases breaks | Extend only final shift; reject unsupported hours |
| P0 | Duplicate material demands/resource alternatives and conflicting routing rows are ambiguous | Reject at canonical model/import boundary |
| P0 | Subminute arrivals/downtime can release capacity early | Round releases and recovery up; downtime starts down |
| P0 | Impact count misses at-risk→late, further lateness and removed orders | Compare every original commitment, disclose worsening |
| P0 | Validator trusts inconsistent operation identity and delivery summaries | Independently reconstruct identity, quantities, dates and outcome |
| P1 | No readiness, provenance/freshness or assumption register | Add traceable readiness and conditional decision context |
| P1 | Solver lacks full run metadata and repeat scenario cache | Versioned fingerprint, bounds, settings, cache provenance |
| P1 | Overtime allowance costs all work; recovery omits premium | Compute incremental working minutes against original calendar |
| P1 | Approvals cannot reject; old comparisons mislabeled current | Persist review decisions and use explicit comparison parent |
| P1 | Imports lack key masters, mappings and rollback | Extend validated onboarding; revision-safe restore |
| P1 | No durable asynchronous jobs, actuals reconciliation or robust rolling horizon | Remain release blockers for unattended live planning until implemented and tested |
| P2 | Default dashboard obscures hero workflow; missing heatmap/dependency views | Improve decision-first navigation and evidence |
| P3 | CAPEX, energy, ML, multi-plant, advanced industry packs | Defer; never present synthetic prediction or ROI |

## Scope decision

Retain the functioning stack and single-company database boundary. Do not pretend SQLite JSON storage is PostgreSQL row-isolated SaaS. Prioritize correctness and transparent decisions, then adoption. No live customer data is replaced, and no approved schedule is silently rebuilt. This audit is a baseline record; the implementation report records verified changes and remaining release gates.
