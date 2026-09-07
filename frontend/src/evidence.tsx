import { useEffect, useState } from "react";
import { Panel } from "./ui";
import { api, fmt, money } from "./api";
import type { Row } from "./api";

export function PlanningEvidence({
  readiness,
  result,
}: {
  readiness?: Row;
  result?: Row;
}) {
  const r = result?.readiness || readiness;
  if (!r) return null;
  return (
    <Panel title="Planning readiness" sub={r.confidence}>
      <div className="detail-body">
        <strong>{r.status}</strong>
        <p>
          Source: {r.source} · Last confirmed:{" "}
          {r.confirmed_at ? fmt(r.confirmed_at, true) : "Not confirmed"}
        </p>
        {r.warnings.map((w: string) => (
          <p className="amber-text" key={w}>
            {w}
          </p>
        ))}
        <details>
          <summary>Checks and assumptions</summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Input</th>
                  <th>Status</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {r.checks.map((c: Row) => (
                  <tr key={c.name}>
                    <td>{c.name}</td>
                    <td>{c.status}</td>
                    <td className="wrap-cell">{c.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul>
            {r.assumptions.map((a: string) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </details>
        {result?.cache && (
          <p className="fine-print">
            {result.cache.hit ? "Reused identical scenario" : "New solve"} ·
            Input revision {result.cache.input_revision} · Solved{" "}
            {fmt(result.cache.solved_at, true)}
          </p>
        )}
        {result?.solver_version && (
          <details>
            <summary>Solver evidence</summary>
            <p>
              {result.solver} {result.solver_version} · {result.solver_status}
            </p>
            <p>{result.objective_name}</p>
            <p>
              Objective: {result.statistics.objective ?? "Unavailable"} · Lower
              bound: {result.statistics.best_bound ?? "Unavailable"} · Solve
              time: {result.statistics.wall_seconds}s
            </p>
          </details>
        )}
        {result?.cost_breakdown && (
          <details>
            <summary>Cost calculation</summary>
            <p>{result.cost_breakdown.basis}</p>
            <p>
              Production: {money(result.cost_breakdown.production)} · Overtime:{" "}
              {result.cost_breakdown.overtime_minutes} min ×{" "}
              {money(result.cost_breakdown.overtime_rate)}/h ={" "}
              {money(result.cost_breakdown.overtime_premium)}
            </p>
            <p>Configured total: {money(result.cost_breakdown.total)}</p>
            <p>Not priced: {result.cost_breakdown.unpriced.join(", ")}</p>
          </details>
        )}
      </div>
    </Panel>
  );
}

export function DependencyEvidence() {
  const [load, setLoad] = useState<Row | null>(null),
    [materials, setMaterials] = useState<Row | null>(null),
    [selected, setSelected] = useState<Row | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    Promise.all([api("/resource-load"), api("/material-impact")])
      .then(([a, b]) => {
        setLoad(a);
        setMaterials(b);
      })
      .catch((e) => setError(e.message));
  }, []);
  return (
    <>
      {error && <p role="alert">{error}</p>}
      <Panel
        title="Resource × day"
        sub={`Approved plan v${load?.version ?? "—"}. Select a cell to see customer commitments.`}
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Resource</th>
                {load?.items[0]?.days.map((d: Row) => (
                  <th key={d.date}>{fmt(d.date)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {load?.items.map((r: Row) => (
                <tr key={r.resource_id}>
                  <td>{r.resource_id}</td>
                  {r.days.map((d: Row) => (
                    <td key={d.date}>
                      <button
                        className={`heat-cell ${d.state === "Unavailable" ? "off" : d.utilization >= 85 ? "hot" : "cool"}`}
                        aria-label={`${r.resource_id} ${d.date}: ${d.state}`}
                        onClick={() =>
                          setSelected({ ...d, resource_id: r.resource_id })
                        }
                      >
                        {d.utilization === null ? "—" : `${d.utilization}%`}
                      </button>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {selected && (
          <div className="detail-body">
            <p>
              {selected.resource_id} · {fmt(selected.date)} · {selected.state}
            </p>
            <p>
              {selected.occupied_minutes} occupied / {selected.capacity_minutes}{" "}
              available minutes
            </p>
            <p>Orders: {selected.orders.join(", ") || "None"}</p>
          </div>
        )}
      </Panel>
      <Panel
        title="Material → product → customer commitments"
        sub={materials?.note}
      >
        <div className="detail-body">
          {materials?.items.map((m: Row) => (
            <details key={m.material_id}>
              <summary>
                {m.material_id} · {m.description} · {m.orders.length} open
                orders{m.quality_hold ? " · QUALITY HOLD" : ""}
              </summary>
              <p>
                Supplier: {m.supplier_id || "Not supplied"} · Available:{" "}
                {m.available} · Incoming: {m.incoming} · ETA:{" "}
                {m.arrival ? fmt(m.arrival, true) : "Not supplied"}
              </p>
              <p>Products: {m.products.join(", ")}</p>
              <ul>
                {m.orders.map((o: Row) => (
                  <li key={o.id}>
                    {o.id} → {o.customer_id} · {o.quantity} units · {o.status}
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </div>
      </Panel>
    </>
  );
}
