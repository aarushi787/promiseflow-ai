# Constraint contract

| Hard | Enforcement |
|---|---|
| Machine, tool, operator capacity | Cumulative intervals with capacity from master |
| Eligibility and skill | Only approved alternatives and qualified operator pools create intervals |
| Calendar, holidays, maintenance | Feasible start domains from intersected calendars minus downtime |
| Order/material release | Releases rounded up to next minute; downtime end rounded up |
| Precedence | Each batch successor starts after predecessor plus transfer/queue |
| Quality/order hold | No operation scheduled; commitment remains blocked |
| Frozen work | Promise fixes approved work; released/in-production or locked operations retain assignment |
| Hard deadline | Order completion cannot exceed supplied deadline |
| Complete publication | Validator rejects omitted operations, blocked work and inconsistent deliveries |

Requested/committed dates are soft and can produce late results. Setup is fixed per transfer batch, not sequence-dependent. Product batch size controls split transfer quantities; no partial customer shipment is implied. Capacity pools currently consume one unit per operation, not arbitrary crew demand. No manufacturing route or supplier is inferred.

Rounding is conservative for releases and unavailable intervals. Input/output timestamps use plant-local time with minute scheduling resolution. The validator reconstructs identity, quantity, duration, release, precedence, capacity, material demand, completion, due date, slack and delivery classification.
