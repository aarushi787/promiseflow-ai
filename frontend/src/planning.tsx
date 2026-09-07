import { useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  ChartBar,
  CheckCircle,
  Clock,
  MagnifyingGlass,
  Package,
  ShieldCheck,
  Target,
  TrendUp,
  Warning,
} from "@phosphor-icons/react";
import { fmt } from "./api";
import type { Data, Row } from "./api";
import { Badge, OrderTable, Panel } from "./ui";
import { DependencyEvidence } from "./evidence";
export function Dashboard({
  data,
  go,
  inspect,
  canPromise,
}: {
  data: Data;
  go: (p: string) => void;
  inspect: (id: string) => void;
  canPromise: boolean;
}) {
  const p = data.plan,
    orders: Row[] = p?.orders || [],
    f = data.factory,
    onTime = orders.filter((o) => o.status === "ON TIME"),
    risk = orders.filter((o) => o.status === "AT RISK"),
    late = orders.filter(
      (o) => o.status === "LATE" || o.status === "UNSCHEDULED",
    );
  const utilization: Row[] =
      p?.bottlenecks?.filter(
        (r: Row) =>
          f.resources.find((x: Row) => x.id === r.resource_id)?.type !==
          "External vendor",
      ) || [],
    avg = utilization.length
      ? Math.round(
          utilization.reduce((s, r) => s + r.utilization, 0) /
            utilization.length,
        )
      : 0;
  const attention = [...late, ...risk].slice(0, 3),
    today = (p?.base || "").slice(0, 10),
    dueToday = f.orders.filter(
      (o: Row) => o.requested_date.slice(0, 10) === today,
    ).length;
  return (
    <>
      <div className="metric-grid">
        {[
          {
            label: "Active customer orders",
            value: orders.length,
            icon: Package,
            sub: dueToday + " due on planning start",
            color: "green",
          },
          {
            label: "On-time commitments",
            value: onTime.length,
            icon: CheckCircle,
            sub: orders.length
              ? Math.round((onTime.length / orders.length) * 100) +
                "% with delivery buffer"
              : "No plan approved",
            color: "green",
          },
          {
            label: "Deliveries need attention",
            value: risk.length + late.length,
            icon: Warning,
            sub: `${risk.length} at risk · ${late.length} projected late / blocked`,
            color: "amber",
          },
          {
            label: "Resource utilization",
            value: avg + "%",
            icon: ChartBar,
            sub: "First 7 days · available capacity",
            color: "green",
          },
        ].map((m, i) => (
          <div
            className={"metric " + (i === 0 ? "featured" : "")}
            key={m.label}
          >
            <div className="metric-top">
              <span>{m.label}</span>
              <m.icon size={21} />
            </div>
            <strong>{m.value}</strong>
            <span className={"metric-foot " + m.color}>
              {i === 1 ? (
                <ShieldCheck size={14} />
              ) : i === 2 ? (
                <Warning size={14} />
              ) : (
                <TrendUp size={14} />
              )}{" "}
              {m.sub}
            </span>
          </div>
        ))}
      </div>
      <div className="overview-grid">
        <Panel
          title="Capacity at a glance"
          sub="Scheduled load across your key resources"
          action={
            <button
              className="text-button"
              onClick={() => go("Production Plan")}
            >
              View production plan <ArrowUpRight size={16} />
            </button>
          }
        >
          <div className="capacity-legend">
            <span>
              <i className="legend-dot green-bg" />
              Planned load
            </span>
            <span>
              <i className="legend-dot amber-bg" />
              Above 85%
            </span>
            <span className="muted">Next 7 days</span>
          </div>
          <div className="capacity-chart">
            {utilization.map((r) => (
              <button
                key={r.resource_id}
                className="chart-column"
                onClick={() => go("Bottlenecks")}
                aria-label={`${r.name}: ${r.utilization}% utilized`}
              >
                <span className={r.utilization >= 85 ? "amber-text" : ""}>
                  {Math.round(r.utilization)}
                  <small>%</small>
                </span>
                <div className="bar-track">
                  <div
                    className={
                      "bar-fill " + (r.utilization >= 85 ? "amber-bg" : "")
                    }
                    style={{ height: r.utilization + "%" }}
                  />
                </div>
                <strong>{r.resource_id}</strong>
              </button>
            ))}
          </div>
          <div className="chart-caption">
            <span>
              <Clock size={15} />
              Load respects shifts, maintenance and capacity.
            </span>
            <button className="text-button" onClick={() => go("Resources")}>
              Availability <ArrowRight size={14} />
            </button>
          </div>
        </Panel>
        <Panel
          title="Needs your attention"
          sub="Resolve risks before they become delays"
          action={
            <span className="count-badge">{risk.length + late.length}</span>
          }
          className="attention-panel"
        >
          {attention.length ? (
            attention.map((o) => {
              const source = f.orders.find((x: Row) => x.id === o.id),
                customer = f.customers.find(
                  (c: Row) => c.id === source?.customer_id,
                );
              return (
                <button
                  className="attention-item"
                  key={o.id}
                  onClick={() => inspect(o.id)}
                >
                  <span
                    className={
                      "attention-icon " +
                      (o.status === "AT RISK" ? "amber" : "red")
                    }
                  >
                    <Warning size={19} />
                  </span>
                  <div>
                    <div>
                      <strong>{o.id}</strong>
                      <Badge value={o.status} />
                    </div>
                    <p>{customer?.name}</p>
                    <span>
                      {o.tardiness_minutes
                        ? `${(o.tardiness_minutes / 1440).toFixed(1)} days after commitment`
                        : "Less than the configured delivery buffer"}
                    </span>
                  </div>
                  <ArrowUpRight size={16} />
                </button>
              );
            })
          ) : (
            <div className="all-clear">
              <CheckCircle size={30} />
              <h3>Your commitments have room to breathe.</h3>
              <p>No current delivery alerts.</p>
            </div>
          )}
          <button className="attention-all" onClick={() => go("Bottlenecks")}>
            Review all constraints <ArrowRight size={17} />
          </button>
        </Panel>
      </div>
      <Panel
        title="Upcoming customer commitments"
        sub="Projected dispatch against the dates you promised"
        action={
          <button className="text-button" onClick={() => go("Orders")}>
            All orders <ArrowRight size={16} />
          </button>
        }
      >
        <OrderTable
          data={data}
          rows={[...orders]
            .sort((a, b) => a.due.localeCompare(b.due))
            .slice(0, 6)}
          inspect={inspect}
        />
      </Panel>
      {canPromise && (
        <div className="insight-strip">
          <span className="insight-icon">
            <Target size={24} />
          </span>
          <div>
            <strong>
              A new order shouldn’t put an existing promise at risk.
            </strong>
            <p>
              Check capacity and compare recovery options before accepting the
              next commitment.
            </p>
          </div>
          <button className="secondary" onClick={() => go("Promise Checker")}>
            Check a delivery date <ArrowRight size={17} />
          </button>
        </div>
      )}
    </>
  );
}
export function Gantt({
  plan,
  factory,
  onSelect,
}: {
  plan: Row;
  factory: Row;
  onSelect: (r: Row) => void;
}) {
  const [days, setDays] = useState(7),
    [resource, setResource] = useState("All resources"),
    [filter, setFilter] = useState(""),
    [highlight, setHighlight] = useState("All operations"),
    [start, setStart] = useState(plan.base.slice(0, 10));
  const origin = new Date(start + "T00:00:00").getTime(),
    span = days * 86400000,
    visible = plan.operations.filter(
      (o: Row) =>
        JSON.stringify(o).toLowerCase().includes(filter.toLowerCase()) &&
        (highlight === "All operations" ||
          plan.orders.find((x: Row) => x.id === o.order_id)?.status ===
            highlight),
    ),
    resources = factory.resources.filter(
      (r: Row) => resource === "All resources" || r.id === resource,
    );
  return (
    <Panel
      title="Production timeline"
      sub="Select an operation to inspect its assignment. Each lane is one unit of capacity."
      action={<span className="subtle-tag">Validated assignments</span>}
    >
      <div className="gantt-tools">
        <div className="search-field">
          <MagnifyingGlass size={17} />
          <input
            aria-label="Filter timeline"
            placeholder="Order, customer ID or product…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
        <select
          aria-label="Resource filter"
          value={resource}
          onChange={(e) => setResource(e.target.value)}
        >
          <option>All resources</option>
          {factory.resources.map((r: Row) => (
            <option key={r.id}>{r.id}</option>
          ))}
        </select>
        <select
          aria-label="Highlight delivery status"
          value={highlight}
          onChange={(e) => setHighlight(e.target.value)}
        >
          {["All operations", "LATE", "AT RISK"].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
        <input
          type="date"
          aria-label="Timeline start date"
          value={start}
          onChange={(e) => setStart(e.target.value)}
        />
        <div className="segmented">
          {[3, 7, 14].map((d) => (
            <button
              className={days === d ? "active" : ""}
              key={d}
              onClick={() => setDays(d)}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>
      <div className="gantt-scroll">
        <div className="gantt" style={{ minWidth: days === 14 ? 1500 : 1000 }}>
          <div className="gantt-header">
            <div>RESOURCE / CAPACITY</div>
            <div className="gantt-dates">
              {Array.from({ length: days }, (_, i) => (
                <span key={i}>
                  {new Date(origin + i * 86400000).toLocaleDateString("en-IN", {
                    weekday: "short",
                    day: "numeric",
                    month: days <= 7 ? "short" : undefined,
                  })}
                </span>
              ))}
            </div>
          </div>
          {resources.map((r: Row) => {
            const ops = visible.filter(
                (o: Row) =>
                  o.resource_id === r.id &&
                  new Date(o.end).getTime() > origin &&
                  new Date(o.start).getTime() < origin + span,
              ),
              laneEnds: number[] = Array(r.capacity).fill(0),
              positioned = ops
                .sort((a: Row, b: Row) => a.start.localeCompare(b.start))
                .map((o: Row) => {
                  const s = new Date(o.start).getTime();
                  let lane = laneEnds.findIndex((e) => e <= s);
                  if (lane < 0) lane = 0;
                  laneEnds[lane] = new Date(o.end).getTime();
                  return { o, lane };
                });
            return (
              <div
                className="gantt-row"
                key={r.id}
                style={{ minHeight: Math.max(82, r.capacity * 36 + 18) }}
              >
                <div className="gantt-label">
                  <strong>{r.id}</strong>
                  <span>{r.name}</span>
                  <small>{r.capacity} × capacity</small>
                </div>
                <div
                  className="gantt-track"
                  style={{ backgroundSize: `${100 / days}% 100%` }}
                >
                  {r.unavailable.map((w: Row, i: number) => {
                    const a = Math.max(
                        0,
                        ((new Date(w.start).getTime() - origin) / span) * 100,
                      ),
                      b = Math.min(
                        100,
                        ((new Date(w.end).getTime() - origin) / span) * 100,
                      );
                    return b > a ? (
                      <button
                        aria-label={w.reason}
                        className="maintenance-bar"
                        key={i}
                        style={{ left: a + "%", width: b - a + "%" }}
                        onClick={() =>
                          onSelect({ title: r.id + " · maintenance", ...w })
                        }
                      />
                    ) : null;
                  })}
                  {positioned.map(({ o, lane }: { o: Row; lane: number }) => {
                    const a = Math.max(
                        0,
                        ((new Date(o.start).getTime() - origin) / span) * 100,
                      ),
                      b = Math.min(
                        100,
                        ((new Date(o.end).getTime() - origin) / span) * 100,
                      );
                    return (
                      <button
                        key={o.id}
                        title={`${o.order_id} · ${o.operation} · ${fmt(o.start, true)} → ${fmt(o.end, true)}`}
                        className={
                          "gantt-bar " +
                          (plan.orders.find((x: Row) => x.id === o.order_id)
                            ?.status === "LATE"
                            ? "late"
                            : o.product_id === factory.products[1]?.id
                              ? "blue"
                              : o.product_id === factory.products[2]?.id
                                ? "ochre"
                                : "")
                        }
                        style={{
                          left: a + "%",
                          width: `max(${b - a}%, 3px)`,
                          top: 10 + lane * 36,
                        }}
                        onClick={() => onSelect(o)}
                      >
                        <strong>{o.order_id}</strong>
                        <span>{o.operation}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div className="gantt-legend">
        <span>
          <i className="legend-dot green-bg" />
          Default product
        </span>
        <span>
          <i className="legend-dot blue-bg" />
          Product 2
        </span>
        <span>
          <i className="legend-dot amber-bg" />
          Product 3
        </span>
        <span>
          <i className="legend-dot red-bg" />
          Projected late
        </span>
        <span className="muted">Hatched areas: downtime</span>
      </div>
    </Panel>
  );
}
export function OperationsTable({ plan }: { plan: Row }) {
  const [search, setSearch] = useState("");
  const ops = plan.operations.filter((o: Row) =>
    JSON.stringify(o).toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <Panel
      title="Operation dispatch list"
      sub="Use job and batch IDs to coordinate the shop floor"
      action={
        <div className="search-field">
          <MagnifyingGlass size={17} />
          <input
            aria-label="Search operation list"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter operations…"
          />
        </div>
      }
    >
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Job / operation</th>
              <th>Resource</th>
              <th>Qty</th>
              <th>Start</th>
              <th>Finish</th>
              <th>Tool / operator</th>
            </tr>
          </thead>
          <tbody>
            {ops.slice(0, 100).map((o: Row) => (
              <tr key={o.id}>
                <td>
                  <strong>{o.job_id}</strong>
                  <span className="cell-sub">{o.operation}</span>
                </td>
                <td>
                  {o.resource_id}
                  {o.locked && <span className="cell-sub">Locked work</span>}
                </td>
                <td>{o.quantity}</td>
                <td>{fmt(o.start, true)}</td>
                <td>{fmt(o.end, true)}</td>
                <td>
                  {o.tool_id || "—"}
                  <span className="cell-sub">
                    {o.operator_id || "No skill constraint"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {ops.length > 100 && (
        <p className="table-note">
          Showing the first 100 matching operations. Filter or export the full
          dispatch list.
        </p>
      )}
    </Panel>
  );
}
export function Bottlenecks({
  data,
  go,
  inspect,
}: {
  data: Data;
  go: (p: string) => void;
  inspect: (id: string) => void;
}) {
  const p = data.plan;
  return (
    <>
      <DependencyEvidence />
      <div className="section-callout">
        <Warning size={24} />
        <div>
          <strong>Capacity is only one part of the delivery picture.</strong>
          <p>
            Review materials, shared fixtures and vendor lead time alongside
            resource utilization.
          </p>
        </div>
        <button className="secondary" onClick={() => go("What-If Simulator")}>
          Test a recovery <ArrowRight size={17} />
        </button>
      </div>
      <Panel
        title="Resource constraints"
        sub="First seven days of the approved plan; finite capacity prevents overload."
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Resource</th>
                <th>Utilization</th>
                <th>Load / capacity</th>
                <th>Affected orders</th>
                <th>Suggested action</th>
              </tr>
            </thead>
            <tbody>
              {p?.bottlenecks?.map((r: Row) => (
                <tr key={r.resource_id}>
                  <td>
                    <strong>{r.resource_id}</strong>
                    <span className="cell-sub">{r.name}</span>
                  </td>
                  <td>
                    <div className="utilization">
                      <span className={r.utilization >= 85 ? "amber-text" : ""}>
                        {r.utilization}%
                      </span>
                      <div>
                        <i
                          style={{ width: r.utilization + "%" }}
                          className={r.utilization >= 85 ? "amber-bg" : ""}
                        />
                      </div>
                    </div>
                  </td>
                  <td>
                    {r.load_hours} / {r.capacity_hours} h
                  </td>
                  <td>
                    <div className="order-chips">
                      {r.affected_orders.slice(0, 3).map((o: string) => (
                        <button key={o} onClick={() => inspect(o)}>
                          {o}
                        </button>
                      ))}
                      {r.affected_orders.length > 3 && (
                        <span>+{r.affected_orders.length - 3}</span>
                      )}
                    </div>
                  </td>
                  <td className="wrap-cell">{r.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <Panel
        title="Delivery alerts"
        sub="Each alert links back to its scheduling evidence."
      >
        <div className="alerts-grid">
          {p?.orders
            .filter((o: Row) => o.status !== "ON TIME")
            .map((o: Row) => (
              <button
                className="alert-card"
                key={o.id}
                onClick={() => inspect(o.id)}
              >
                <div>
                  <Badge value={o.status} />
                  <ArrowUpRight size={17} />
                </div>
                <h3>{o.id}</h3>
                <p>
                  {o.reason ||
                    `Projected dispatch ${fmt(o.completion, true)} against commitment ${fmt(o.due, true)}.`}
                </p>
                <span>
                  Review evidence and recovery actions <ArrowRight size={14} />
                </span>
              </button>
            ))}
        </div>
      </Panel>
    </>
  );
}
