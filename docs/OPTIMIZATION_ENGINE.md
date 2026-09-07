# Optimization engine

`SolverProvider` separates the application from `CpSatProvider`. The actual schedule comes from OR-Tools CP-SAT optional intervals and cumulative capacity constraints. Greedy earliest-slot assignments are hints only. No LLM is involved.

Every operation selects exactly one approved machine and, when required, a qualified operator. The operation, setup, vendor lead time and transit occupy a contiguous resource window. Product transfer batches follow linear precedence including transfer/queue lag. Material allocation is a conservative deterministic preallocation, not jointly optimized with sequencing.

Promise mode minimizes new-order completion with approved operations fixed. Only OPTIMAL in that mode proves the earliest completion **under this input model and allocation policy**. General planning uses a configurable weighted sum of priority-weighted late orders, tardiness, makespan and production cost. It is not a strict lexicographic hierarchy. Cost and utilization cannot be described as globally optimal when status is FEASIBLE.

Results store model version, OR-Tools version, seed 42, one worker, 0.3 deterministic time budget, 30-second solver wall limit, status, objective, best bound, solve time, and hard/soft constraint lists. The wall limit excludes model construction. Wall-limit termination can reduce repeatability; deterministic is false near that limit. UNKNOWN and INFEASIBLE retain customer outcomes as unscheduled and do not imply the requested date is mathematically impossible under every alternative.

Independent validation precedes publication. The scope guard is 1,200 batch operations. Larger factories require an explicitly designed rolling horizon/decomposition strategy; the application does not silently drop work to fit the limit.
