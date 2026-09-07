# V3.1 — Shop-floor actuals and conservative reconciliation

This increment closes the first part of the highest-ranked V3 audit gap. Inspection showed the optimizer reconstructs every routing operation at full quantity; sending partial actuals into that model would repeat production and consume material twice. The approved schedule, independent validator, transaction revision checks and existing CP-SAT stack are preserved.

## Implemented workflow

1. Open **Shop Floor** with an approved schedule. Supervisor, planner, manager and administrator can record START, PROGRESS, PAUSE, BREAKDOWN, HOLD, RESUME and COMPLETE.
2. Select the approved operation, enter the observed plant-local time, cumulative good quantity and reason. The log enforces plant-wide chronological entry. No future timestamps, zero-length completions, missing predecessors, skipped transfer delays or overlapping running resource/tool/operator capacity are accepted.
3. PROGRESS must increase cumulative quantity below batch size. COMPLETE requires the full batch. Pause events preserve quantity; resume preserves quantity. Only a manager or administrator can resume held work. Pause/breakdown/hold release tracked occupancy; this is a conservative event-state model, not a physical fixture-retention model.
4. Actuals increment the factory revision, invalidate previous proposals and block further solves, master replacement/import application and publication. Existing approved snapshots remain immutable; their delivery projections are explicitly labeled unreconciled in the interface.
5. Complete every batch operation of every observed order. A manager or administrator confirms current stock, reservations, incoming quantity and arrival for exactly the materials used by those orders. These are observed balances **after** consumption/receipts; the system does not deduct theoretical consumption again.
6. Reconciliation atomically stores closures and balance changes, marks those orders COMPLETED, and advances the planning epoch and `planning_not_before` boundary. The remaining plan must still be generated, reviewed and explicitly published. Completed work is excluded and identified as completed in commitment comparisons, not as a newly lost commitment.

## Safety and persistence

- `actual_events` is append-only through the application. Each row retains actor, server recording time, observed time, approved version, operation, event, quantity and reason. Request IDs make exact retries idempotent; reuse with changed content is rejected.
- `execution_closures` retains order, manager, time and reason. Reconciliation writes balance before/after evidence to the audit log. No endpoint deletes or edits actual events.
- A manager can void the latest uncorrected event before reconciliation. `actual_corrections` preserves the original event, correction actor, time and reason; replay skips voided events. Corrections invalidate prior proposals. Reconciled history cannot be voided.
- All writes use `BEGIN IMMEDIATE`. Event revision checks, solve-save checks and publication checks prevent stale plans from winning a race with new actuals.
- Reconciled orders cannot be reopened, removed or assigned a different product/quantity. Use a new order ID for new work. The enforced boundary cannot be cleared or moved backwards through master edits, imports or activation.
- Solver and independent publication validator both enforce the boundary, rounding fractional release minutes upwards.
- Starting more work requires current master inputs to match the approved snapshot. Existing running work can still be completed during the reconciliation workflow.
- This release adds SQLite tables (schema marker 4); it does not replace the database. Take an online backup before rollout. Existing version inputs missing the new optional boundary remain readable.

## API

`GET /api/execution` returns approved operation rows plus cumulative quantities, remaining quantities, start/finish actuals, finish variance, event history, pending orders, material balances and closures.

`POST /api/execution/events` accepts `request_id`, `revision`, `version_id`, `operation_id`, `kind`, `occurred_at`, `quantity_completed`, `reason`.

`POST /api/execution/reconcile` accepts `revision`, `reason`, and `balances` with `material_id`, `stock`, `reserved`, `incoming`, `arrival`. Manager/administrator only. Validation errors roll back the entire transaction, including closures.

`POST /api/execution/events/{id}/void` accepts `revision` and `reason`. Manager/administrator only; latest uncorrected event of unreconciled production only.

OpenAPI contains the typed schemas. Responses follow existing 401/403 authentication/role, 409 conflict and 422 input-validation conventions.

## Explicit remaining limits

This is a supervised whole-order workflow, not continuous MES integration. While any observed order is partially finished, **all planning is blocked**. Remaining quantity is an observation, not a calculated remaining processing-time estimate. There is no automatic live inventory consumption, partial-batch scheduling, setup-restart policy, resource reassignment, scrap/rework, arbitrary historical corrections/backfill, clock advancement on every request, or cycle-time calibration. Corrections are limited to undoing the latest uncorrected event before reconciliation; confirm these limits are acceptable in the pilot operating procedure.

Recording an event is evidence of what happened, not authorization to run machinery. Calendar variance is retained rather than rewritten into the planned calendar. Material substitutions and manufacturing standards are unchanged. Only supplied/observed data is used; no LLM or predictive score is involved.

## Validation

`tests/test_execution.py` exercises event permissions, hold release, idempotency, stale revisions, quantities, precedence, shared capacity, timestamps, transactional rollback, preservation of the approved plan, full completion/reconciliation/replan/publication, prevention of reopening, and independent enforcement of the current-time boundary. UI verification uses the existing synthetic plan without recording or approving live demo events.

Verification on 7 September 2026: the complete suite passed **87 tests** (75 existing plus 12 execution tests). Production build and lint passed. Filtering and the event dialog were inspected at the normal desktop width and 390 × 844; no actual events or schedule publications were created in the saved demo database. Dependency deprecation warnings remain in the existing TestClient stack.
