# PromiseFlow frontend

React 19 + TypeScript + Vite, Phosphor icons and responsive custom CSS.

Run `npm ci`, then `npm run dev`. The Python API must run on 127.0.0.1:8017; Vite proxies `/api`. `npm run build` creates `dist`, which FastAPI serves in the single-server deployment. `npm run lint` checks the frontend.

`App.tsx` owns session/navigation, `planning.tsx` contains overview/Gantt/constraints, `decisions.tsx` contains promises/scenarios/approvals, and `masters.tsx` contains data maintenance/imports/reports/settings. Shared controls and HTTP helpers live in `ui.tsx` and `api.ts`.

See the root README and docs directory for manufacturing assumptions, API contracts, security, tests and deployment.
