# Scenarios, costs and decisions

Every scenario modifies a deep copy, solves it, and persists a separate proposal. The approved plan changes only through manager/admin activation. Promise Checker can compare reoptimization, a four-hour bottleneck extension and 48-hour incoming-material expedition. These are hypotheses, not guaranteed recoveries. The planner must configure approved resource/vendor alternatives first.

The impact comparison traverses every previous customer commitment, including removed orders, at-risk-to-late changes and further delays to already-late orders. `newly_at_risk` is retained for API compatibility but now counts **worsened commitments**. Current-comparison evidence is recalculated when fetching a historical version; its stored original comparison remains immutable.

Costs: production equals rounded occupied resource hours × configured hourly rate plus quantity × routing unit charge. Overtime premium equals scheduled minutes outside the original resource calendar ÷ 60 × supplied premium. Existing shift breaks are preserved. Recovery cost change in Promise Checker compares the same new-order workload against its no-recovery proposal. Unpriced transport, labour, expedite and penalty charges remain explicitly excluded. No ROI/profit claim is made.

Reviewers can save a note, reject, or approve. Rejection is terminal for that proposal; create a new one to reconsider. Published versions cannot be rejected or overwritten. Stale input revisions/active parents prevent activation. Decision JSON exports include input snapshot, result, solver metadata, decisions and comparison.

Identical solved scenarios use a database-local cache keyed by full factory input, planning epoch, fixed assignments/options, input revision, active version, model and solver version. Settings include source/confirmation freshness data. Each result exposes hit status, fingerprint, source revision and original solve time. Readiness is refreshed on retrieval. Cache retains at most 100 results and never activates them.
