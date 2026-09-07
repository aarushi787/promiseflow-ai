# Ranked release roadmap

1. **P1 — Execution reconciliation:** V3.1 now records actual events and remaining quantities, closes fully completed observed orders with explicit material-balance confirmation, and advances an enforced planning boundary. Remaining: partial-work optimization, lot-level inventory ownership, rework/scrap, event correction/backfill, frozen-zone controls and continuous current-time advancement. Required for live continuous planning; see EXECUTION.md.
2. **P1 — Manufacturing approval and costing:** formal quality releases, operation-scoped alternative/outsource approval, supplier quotes, explicit fees and cost completeness; multi-lot material allocation.
3. **P1 — Deployment acceptance:** HTTPS, restore drill, penetration testing, bounded request ingress, observability/retention and durable worker crash recovery without manual retry.
4. **P1 — Planning quality:** strict configurable objective hierarchy, schedule stability, operation locks/manual moves with revalidation, exact infeasibility evidence and rolling-horizon decomposition.
5. **P2 — Adoption:** guided column mapping, downloadable error workbook, per-cell lineage, dedicated master forms, printable decision reports and a validated fabrication pack.
6. **P2 — Scale:** large Gantt virtualization, broader representative benchmarks, PostgreSQL persistence/migrations and shared-tenancy isolation only when required by rollout.
7. **P3 — Future:** ML after sufficient actuals, CAPEX, energy, sustainability, multi-plant planning and optional controlled language interface. No fabricated ROI or synthetic predictive claims.
