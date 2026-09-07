# Performance and limits

Measured on Windows 11, Python 3.12.10. The reproducible results are in `benchmark-results.json`; run `python -m backend.benchmark`. Synthetic benchmark routes use four/five sequential operations with two alternatives and continuous calendars. This is a scope and feasibility test, not a representative benchmark for every factory.

| Orders | Operations | Resources | Result | Total seconds |
|---:|---:|---:|---|---:|
| 50 | 200 | 10 | FEASIBLE; independently validated | 2.785 |
| 500 | 2,500 | 50 | Rejected by 1,200-operation limit | 0.004 |
| 2,000 | 10,000 | 150 | Rejected by 1,200-operation limit | 0.020 |

The larger rows are **not solve timings**. CP-SAT has a 0.3 deterministic search budget and 30-second solve wall cap, excluding model construction. Fixed seed and one worker aid reproducibility; wall-limit truncation can vary across hardware. Feasible does not mean optimal.

The UI submits persisted background jobs and polls once per second. Queued jobs can be cancelled via API; running solves finish into unapproved proposals. Restart marks queued/running jobs INTERRUPTED for explicit retry. There is no distributed worker failover. Completed jobs and versions persist; production retention policy must be configured operationally.

The Gantt filters by date/resource and limits dispatch-table display to 100 rows, but does not virtualize 5,000 operations. Large Gantt stress tests and rolling horizon are not implemented. Scope rejection is preferable to silent truncation of manufacturing commitments.
