# Excel-first onboarding

Download templates from Imports or `/api/templates/{kind}`. Supported: Customers, Suppliers, Shifts, Resources (Machines alias), Materials, Routing, Products, Operators, Tools and Maintenance. Import in dependency order: customers/suppliers/calendars → resources/materials/auxiliaries → routing → products → orders. Tool references may require tools before routing.

Use XLSX with the named template sheet or UTF-8 CSV. Five MB compressed and 30 MB expanded XLSX limits; 2,000 data rows. Formula cells, macros, external workbook links, invalid MIME types, missing/duplicate headers and corrupt references are rejected. Exports escape formula-like strings including leading whitespace/control characters. Workbooks are never executed.

Optional mapping is a JSON object from source headers to canonical headers, for example `{"Order No":"id"}`. The current UI exposes this as an advanced mapping field. List fields such as material requirements, weekdays and eligible resources use JSON arrays. Dates are ISO plant-local values; cycle/setup/transfer durations use minutes. Material quantities must use the configured material unit; automatic conversion is not implemented.

Preview reports row/column errors and proposed adds/updates. Nothing changes until Apply. A preview is bound to its creator and master revision and cannot be replayed. Matching IDs update; omitted rows are not deleted. Repeated routing alternatives must agree on operation fields. Maintenance rows append distinct unavailable windows; their import IDs identify rows rather than permanent event records.

Undo last import restores the complete pre-import master snapshot only if there have been no subsequent edits or activation. Rollback increments the revision and does not change the active plan. After intervening changes, preview a corrected import rather than discarding other work. Detailed per-cell source lineage and downloadable error-workbook generation remain future onboarding work.
