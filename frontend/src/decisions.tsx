import { useEffect, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  ArrowsClockwise,
  CalendarBlank,
  Check,
  CheckCircle,
  Clock,
  GearSix,
  GitBranch,
  Play,
  Plus,
  ShieldCheck,
  Target,
  Truck,
  Users,
  Warning,
  Wrench,
} from "@phosphor-icons/react";
import { api, post, fmt, money, futureDate, statusClass } from "./api";
import type { Data, Row, Run } from "./api";
import { Badge, Empty, Field, Modal, OrderFields, Panel } from "./ui";
import { PlanningEvidence } from "./evidence";
function ReviewActions({
  id,
  canApprove,
  busy,
  run,
  notice,
  onDecision,
}: {
  id: number;
  canApprove: boolean;
  busy: boolean;
  run: Run;
  notice: (s: string) => void;
  onDecision: () => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const decide = (action: string) =>
    run("Recording decision", async () => {
      await post(`/versions/${id}/decision`, { action, reason });
      await onDecision();
      notice(
        action === "REJECTED"
          ? "Proposal rejected. It cannot be activated."
          : "Saved for review with your note.",
      );
      setReason("");
    });
  return (
    <>
      <input
        aria-label="Decision reason"
        placeholder="Reason for this decision (required)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        maxLength={1000}
      />
      <button
        className="secondary"
        disabled={busy || reason.trim().length < 5}
        onClick={() => decide("SAVED FOR REVIEW")}
      >
        Save for review
      </button>
      {canApprove && (
        <button
          className="secondary"
          disabled={busy || reason.trim().length < 5}
          onClick={() => decide("REJECTED")}
        >
          Reject proposal
        </button>
      )}
    </>
  );
}
export function PromiseChecker({
  data,
  busy,
  run,
  onProposal,
}: {
  data: Data;
  busy: boolean;
  run: Run;
  onProposal: (p: Row) => void;
}) {
  const [value, setValue] = useState<Row>({
    id: "PO-4421",
    customer_id: data.factory.customers[0]?.id || "",
    product_id:
      data.factory.products.find((p: Row) => p.id === "GS-204")?.id ||
      data.factory.products[0]?.id ||
      "",
    quantity: 500,
    requested_date: futureDate(data, 4),
    order_date: data.plan?.base || new Date().toISOString().slice(0, 19),
    priority: "High",
    status: "NEW",
  });
  const [result, setResult] = useState<Row | null>(null),
    [options, setOptions] = useState<Row[]>([]);
  const check = () =>
    run("Checking this delivery promise", async () => {
      setResult(await post("/promise", value));
      setOptions([]);
    });
  const recovery = (kind: string, target = "") =>
    run("Comparing a recovery option", async () => {
      const r = await post(`/versions/${result?.id}/recover`, { kind, target });
      setOptions((prev) => [
        ...prev,
        { ...r, label: kind.replaceAll("_", " ") },
      ]);
    });
  return (
    <>
      <PlanningEvidence readiness={data.readiness} result={result?.result} />
      <div className="promise-layout">
        <Panel
          title="The customer’s request"
          sub="Check without changing your approved schedule"
          className="promise-form"
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              check();
            }}
          >
            <OrderFields
              data={data}
              value={value}
              onChange={(v) => {
                setValue(v);
                setResult(null);
                setOptions([]);
              }}
            />
            <div className="promise-safety">
              <ShieldCheck size={21} />
              <p>
                Existing approved operations stay fixed. Review blocked work,
                data freshness and every customer commitment before accepting.
              </p>
            </div>
            <button disabled={busy} className="primary full">
              <Target size={20} />
              Check delivery feasibility <ArrowRight size={18} />
            </button>
          </form>
        </Panel>
        <section
          className={
            "promise-result " +
            (result ? statusClass(result.promise_status || "") : "")
          }
        >
          {result ? (
            <>
              <div className="result-eyebrow">
                <Target size={20} />
                PROMISE RESULT
              </div>
              <Badge value={result.promise_status || "AT RISK"} />
              <h2>
                {result.promise_status === "FEASIBLE"
                  ? "Yes. There’s room for this promise."
                  : result.promise_status === "NOT FEASIBLE"
                    ? "This date needs a different plan."
                    : "This promise needs a closer look."}
              </h2>
              <div className="promise-dates">
                <div>
                  <span>Requested delivery</span>
                  <strong>{fmt(value.requested_date)}</strong>
                </div>
                <ArrowRight size={23} />
                <div>
                  <span>
                    {result.result.earliest_proven
                      ? "Earliest feasible dispatch"
                      : "Best dispatch found"}
                  </span>
                  <strong>{fmt(result.candidate?.completion)}</strong>
                </div>
              </div>
              <p className="result-note">
                {result.result.earliest_proven
                  ? "Earliest completion proven for this model with approved operations fixed."
                  : "The solver has not proven an earliest date. Review the status and constraints before committing."}
              </p>
              <div className="promise-proof">
                <CheckCircle size={17} />
                {result.result.comparison?.newly_at_risk || 0} existing customer
                commitments worsened
              </div>
              {result.result.message && <p>{result.result.message}</p>}
              <button className="secondary" onClick={() => onProposal(result)}>
                Review proposed schedule <ArrowUpRight size={17} />
              </button>
            </>
          ) : (
            <>
              <div className="result-eyebrow">
                <ShieldCheck size={20} />
                BUILT ON YOUR FACTORY’S REALITY
              </div>
              <div className="promise-illustration">
                <Target size={62} weight="duotone" />
              </div>
              <h2>
                Know before
                <br />
                you say yes.
              </h2>
              <p>
                One check brings together capacity, material, working calendars
                and your existing promises.
              </p>
              <div className="check-list">
                <span>
                  <Check size={16} />
                  {data.factory.resources.length} resources checked
                </span>
                <span>
                  <Check size={16} />
                  {data.plan?.orders.length || 0} existing commitments protected
                </span>
                <span>
                  <Check size={16} />A plan you can explain
                </span>
              </div>
            </>
          )}
        </section>
      </div>
      {result && (
        <>
          <Panel
            title="What’s shaping this delivery?"
            sub="Traceable observations from the factory model"
          >
            <div className="reasons-grid">
              {result.explanations?.map((e: Row, i: number) => (
                <div className="reason" key={i}>
                  <span className="reason-number">{i + 1}</span>
                  <div>
                    <strong>{e.kind}</strong>
                    <p>{e.cause}</p>
                    <span>{e.action}</span>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
          <Panel
            title="How could we meet the requested date?"
            sub="Recovery options may move existing work. Compare the impact before approval."
          >
            <div className="recovery-actions">
              <button
                className="secondary"
                disabled={busy}
                onClick={() => recovery("resequence")}
              >
                <ArrowsClockwise size={18} />
                Optimize sequence & eligible machines
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  recovery(
                    "overtime",
                    data.plan?.bottlenecks?.find(
                      (r: Row) =>
                        data.factory.resources.find(
                          (x: Row) => x.id === r.resource_id,
                        )?.type !== "External vendor",
                    )?.resource_id || data.factory.resources[0]?.id,
                  )
                }
              >
                <Clock size={18} />
                Extend bottleneck shift by 4h
              </button>
              {data.factory.materials.some((m: Row) => m.incoming > 0) && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    recovery(
                      "expedite_material",
                      data.factory.materials.find((m: Row) => m.incoming > 0)
                        .id,
                    )
                  }
                >
                  <Truck size={18} />
                  Expedite material by 48h
                </button>
              )}
            </div>
            {options.length > 0 && (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Recovery proposal</th>
                      <th>Dispatch</th>
                      <th>Production cost change</th>
                      <th>Existing commitments worsened</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {options.map((p, i) => (
                      <tr key={p.id}>
                        <td>
                          Option {String.fromCharCode(65 + i)} · v{p.id}
                          <span className="cell-sub">{p.label}</span>
                          <span className="cell-sub">
                            {p.result.solver_status}
                          </span>
                        </td>
                        <td>
                          {fmt(
                            p.result.orders.find((o: Row) => o.id === value.id)
                              ?.completion,
                            true,
                          )}
                        </td>
                        <td>
                          {money(
                            (p.result.cost_breakdown?.total ?? p.result.cost) -
                              (result.result.cost_breakdown?.total ??
                                result.result.cost),
                          )}
                          <span className="cell-sub">
                            Versus same order without recovery; unpriced fees
                            excluded
                          </span>
                        </td>
                        <td>{p.result.comparison?.newly_at_risk ?? "—"}</td>
                        <td>
                          <button
                            className="text-button"
                            onClick={() => onProposal(p)}
                          >
                            Compare plan <ArrowRight size={15} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </>
      )}
    </>
  );
}
export function Simulator({
  data,
  disruption,
  allowed,
  busy,
  run,
  onProposal,
}: {
  data: Data;
  disruption: boolean;
  allowed: boolean;
  busy: boolean;
  run: Run;
  onProposal: (p: Row) => void;
}) {
  const types = [
    ["breakdown", "Machine breakdown", "resources", Wrench],
    ["material_delay", "Material delay", "materials", Truck],
    ["operator_absence", "Operator absence", "auxiliaries", Users],
    ["overtime", "Overtime", "resources", Clock],
    ["additional_shift", "Additional shift", "resources", CalendarBlank],
    ["maintenance", "Maintenance extension", "resources", GearSix],
    ["supplier_delay", "Supplier delay", "suppliers", Truck],
    ["production_delay", "Production delay", "resources", Clock],
    ["quality_hold", "Material quality hold", "materials", ShieldCheck],
    ["quantity", "Quantity increase", "orders", Plus],
    ["delivery_date", "Delivery-date change", "orders", CalendarBlank],
    ["alternative_machine", "Alternative machine", "resources", GearSix],
    ["outsource", "Qualified outsourcing", "resources", Truck],
    ["split_quantity", "Split transfer batches", "products", GitBranch],
  ] as const;
  const [kind, setKind] = useState("breakdown"),
    [target, setTarget] = useState(data.factory.resources[0]?.id || ""),
    [hours, setHours] = useState(6),
    [start, setStart] = useState(futureDate(data, 1, 8)),
    [quantity, setQuantity] = useState(500),
    [date, setDate] = useState(futureDate(data, 3)),
    [reason, setReason] = useState(""),
    [events, setEvents] = useState<Row[]>([]);
  useEffect(() => {
    api("/events")
      .then(setEvents)
      .catch(() => {});
  }, []);
  const type = types.find((x) => x[0] === kind)!,
    targets = data.factory[type[2]].filter(
      (x: Row) =>
        (kind !== "operator_absence" || x.kind === "Operator") &&
        (kind !== "outsource" || x.type === "External vendor"),
    );
  return (
    <>
      <div className="simulation-layout">
        <div>
          <div className="scenario-grid">
            {types.map(([key, name, table, Icon]) => (
              <button
                className={"scenario-tile " + (key === kind ? "selected" : "")}
                key={key}
                onClick={() => {
                  setKind(key);
                  setTarget(
                    data.factory[table].find(
                      (x: Row) =>
                        (key !== "operator_absence" || x.kind === "Operator") &&
                        (key !== "outsource" || x.type === "External vendor"),
                    )?.id || "",
                  );
                }}
              >
                <Icon size={23} />
                <strong>{name}</strong>
                <span>
                  {key === kind ? (
                    <CheckCircle size={16} weight="fill" />
                  ) : (
                    <Plus size={15} />
                  )}
                </span>
              </button>
            ))}
          </div>
          <div className="simulation-note">
            <GitBranch size={22} />
            <div>
              <strong>A safe space to change the plan.</strong>
              <p>
                Your approved schedule stays active while you explore scenarios.
                A production manager or administrator must activate a proposal.
              </p>
            </div>
          </div>
        </div>
        <Panel
          title={type[1]}
          sub={
            disruption
              ? "Record an event and evaluate its impact."
              : "Change one assumption and compare the result."
          }
        >
          <form
            className="detail-body"
            onSubmit={(e) => {
              e.preventDefault();
              run("Simulating " + type[1].toLowerCase(), async () =>
                onProposal(
                  await post("/scenario", {
                    kind,
                    target,
                    start,
                    hours,
                    quantity: ["quantity", "split_quantity"].includes(kind)
                      ? quantity
                      : undefined,
                    date: kind === "delivery_date" ? date : undefined,
                    reason,
                  }),
                ),
              );
            }}
          >
            <Field label="Affected item">
              <select
                required
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              >
                {targets.map((x: Row) => (
                  <option key={x.id} value={x.id}>
                    {x.id} · {x.name || x.description || x.product_id}
                  </option>
                ))}
              </select>
            </Field>
            {![
              "quantity",
              "delivery_date",
              "outsource",
              "alternative_machine",
              "split_quantity",
            ].includes(kind) && (
              <>
                <Field
                  label={
                    kind === "overtime" || kind === "additional_shift"
                      ? "Additional hours per working day"
                      : "Duration / delay (hours)"
                  }
                >
                  <input
                    type="number"
                    min="1"
                    max={
                      ["overtime", "additional_shift"].includes(kind) ? 8 : 720
                    }
                    value={hours}
                    onChange={(e) => setHours(Number(e.target.value))}
                    required
                  />
                </Field>
                <Field label="Event start (plant time)">
                  <input
                    type="datetime-local"
                    value={start}
                    onChange={(e) => setStart(e.target.value)}
                    required
                  />
                </Field>
              </>
            )}
            {["quantity", "split_quantity"].includes(kind) && (
              <Field
                label={
                  kind === "quantity"
                    ? "New order quantity"
                    : "Transfer batch quantity"
                }
              >
                <input
                  type="number"
                  min="1"
                  value={quantity}
                  onChange={(e) => setQuantity(Number(e.target.value))}
                />
              </Field>
            )}
            {kind === "delivery_date" && (
              <Field label="New commitment">
                <input
                  type="datetime-local"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                />
              </Field>
            )}
            <Field label="Planner’s note">
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="What changed, and why?"
                maxLength={500}
              />
            </Field>
            {["overtime", "additional_shift"].includes(kind) && (
              <p className="fine-print">
                Extends this resource across the planning horizon. Operator
                calendars remain unchanged and may still constrain work.
              </p>
            )}
            <button className="primary full" disabled={busy || !allowed}>
              <Play size={17} weight="fill" />
              Simulate impact
            </button>
            {!allowed && (
              <p className="fine-print">
                Your role has read-only access to scenarios.
              </p>
            )}
          </form>
        </Panel>
      </div>
      {disruption && (
        <Panel
          title="Event history"
          sub="Recorded scenarios and the proposal created for each event."
        >
          {events.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Event</th>
                    <th>Target</th>
                    <th>Recorded</th>
                    <th>By</th>
                    <th>Proposal</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((e) => (
                    <tr key={e.id}>
                      <td>{e.body.kind.replaceAll("_", " ")}</td>
                      <td>{e.body.target}</td>
                      <td>{fmt(e.created_at, true)}</td>
                      <td>{e.actor}</td>
                      <td>v{e.version_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title="No disruption scenarios recorded"
              body="Simulate an event above to evaluate its effect on production."
            />
          )}
        </Panel>
      )}
    </>
  );
}
export function Versions({
  data,
  proposal,
  setProposal,
  canApprove,
  canWrite,
  busy,
  run,
  refresh,
  newPlan,
  notice,
}: {
  data: Data;
  proposal: Row | null;
  setProposal: (p: Row | null) => void;
  canApprove: boolean;
  canWrite: boolean;
  busy: boolean;
  run: Run;
  refresh: () => Promise<void>;
  newPlan: () => Promise<void>;
  notice: (s: string) => void;
}) {
  const [versions, setVersions] = useState<Row[]>([]),
    [confirm, setConfirm] = useState(false);
  useEffect(() => {
    api("/versions")
      .then((r) => setVersions(r.items))
      .catch(() => {});
  }, [proposal, data.active_version]);
  const p = proposal?.result,
    impacts: Row[] =
      proposal?.current_comparison?.impacts || p?.comparison?.impacts || [],
    moved: Row[] =
      proposal?.current_comparison?.moved || p?.comparison?.moved || [],
    valid =
      p &&
      ["FEASIBLE", "OPTIMAL"].includes(p.solver_status) &&
      !Object.keys(p.blocked).length;
  return (
    <>
      {proposal && p ? (
        <>
          <div className="comparison-banner">
            <div>
              <GitBranch size={25} />
              <div>
                <strong>
                  Current plan v{data.active_version || "—"} <span>→</span>{" "}
                  Proposed plan v{proposal.id}
                </strong>
                <p>
                  The current plan stays active until you approve this proposal.
                </p>
              </div>
            </div>
            <button
              className="primary"
              disabled={
                busy ||
                !canApprove ||
                !valid ||
                data.active_version === proposal.id ||
                proposal.decisions?.at(-1)?.action === "REJECTED"
              }
              onClick={() => setConfirm(true)}
            >
              <ShieldCheck size={18} />
              Approve & activate
            </button>
          </div>
          <PlanningEvidence result={p} />
          <div className="recovery-actions">
            <a
              className="secondary"
              href={`/api/versions/${proposal.id}/report`}
              download
            >
              Export decision evidence
            </a>
            {(canWrite || canApprove) && (
              <ReviewActions
                onDecision={async () =>
                  setProposal(await api(`/versions/${proposal.id}`))
                }
                id={proposal.id}
                canApprove={canApprove}
                busy={busy}
                run={run}
                notice={notice}
              />
            )}
          </div>
          {!canApprove && (
            <p className="fine-print">
              Activation requires a production manager or administrator.
            </p>
          )}
          <div className="metric-grid">
            <div className="metric">
              <span>Operations evaluated</span>
              <strong>{p.operations.length}</strong>
              <span className="metric-foot">
                {moved.length} assignments changed
              </span>
            </div>
            <div className="metric">
              <span>Commitments worsened</span>
              <strong className="amber-text">
                {impacts.filter((i) => i.newly_at_risk).length}
              </strong>
              <span className="metric-foot">Existing customer commitments</span>
            </div>
            <div className="metric">
              <span>Recovered deliveries</span>
              <strong>
                {
                  impacts.filter(
                    (x) =>
                      x.before_status !== "ON TIME" &&
                      x.after_status === "ON TIME",
                  ).length
                }
              </strong>
              <span className="metric-foot">Now on time with buffer</span>
            </div>
            <div className="metric">
              <span>Production cost change</span>
              <strong className="cost-metric">
                {money(
                  (p.cost_breakdown?.total ?? p.cost) -
                    (data.plan?.cost_breakdown?.total ?? data.plan?.cost ?? 0),
                )}
              </strong>
              <span className="metric-foot">Routing cost estimate</span>
            </div>
          </div>
          {p.message && <div className="message error">{p.message}</div>}
          {Object.keys(p.blocked).length > 0 && (
            <div className="message error">
              <Warning size={20} />
              <div>
                <strong>Unscheduled work prevents activation</strong>
                {Object.entries(p.blocked).map(([id, reason]) => (
                  <p key={id}>
                    {id}: {String(reason)}
                  </p>
                ))}
              </div>
            </div>
          )}
          <Panel
            title="Customer commitment impact"
            sub="Positive delay means later dispatch. Every existing order is shown."
            action={<Badge value={p.solver_status} />}
          >
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Current dispatch</th>
                    <th>Proposed dispatch</th>
                    <th>Change</th>
                    <th>Before</th>
                    <th>After</th>
                  </tr>
                </thead>
                <tbody>
                  {impacts.map((i) => (
                    <tr key={i.order_id}>
                      <td>
                        <strong>{i.order_id}</strong>
                      </td>
                      <td>{fmt(i.before, true)}</td>
                      <td>{fmt(i.after, true)}</td>
                      <td
                        className={
                          i.delay_minutes > 0
                            ? "red-text"
                            : i.delay_minutes < 0
                              ? "green-text"
                              : ""
                        }
                      >
                        {i.delay_minutes === null
                          ? "Unscheduled"
                          : i.delay_minutes === 0
                            ? "No change"
                            : `${i.delay_minutes > 0 ? "+" : ""}${(i.delay_minutes / 60).toFixed(1)} h`}
                      </td>
                      <td>
                        <Badge value={i.before_status} />
                      </td>
                      <td>
                        <Badge value={i.after_status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel
            title="Proposed delivery outcomes"
            sub="Includes new orders absent from the current plan."
          >
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Projected dispatch</th>
                    <th>Due</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {p.orders.map((o: Row) => (
                    <tr key={o.id}>
                      <td>{o.id}</td>
                      <td>{fmt(o.completion, true)}</td>
                      <td>{fmt(o.due, true)}</td>
                      <td>
                        <Badge value={o.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          {moved.length > 0 && (
            <Panel
              title="Recommended operation moves"
              sub={`${moved.length} changes from the approved plan. First 30 shown.`}
            >
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Operation</th>
                      <th>Current resource</th>
                      <th>Proposed resource</th>
                      <th>Current start</th>
                      <th>Proposed start</th>
                    </tr>
                  </thead>
                  <tbody>
                    {moved.slice(0, 30).map((m) => (
                      <tr key={m.id}>
                        <td>{m.id}</td>
                        <td>{m.from_resource}</td>
                        <td>{m.to_resource}</td>
                        <td>{fmt(m.before, true)}</td>
                        <td>{fmt(m.after, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
          <p className="fine-print">
            {p.optimal
              ? "Configured objective solved to optimality."
              : "Feasible results may not be optimal; the solver has a bounded search budget."}{" "}
            Cost excludes unconfigured transport, penalties and expedite fees.
          </p>
        </>
      ) : (
        <div className="section-callout">
          <GitBranch size={28} />
          <div>
            <strong>Every change starts with a proposal.</strong>
            <p>
              Rebuild the production plan or select a saved version to compare
              it.
            </p>
          </div>
          {canWrite && (
            <button className="primary" disabled={busy} onClick={newPlan}>
              Build proposed plan <ArrowRight size={17} />
            </button>
          )}
        </div>
      )}
      <Panel
        title="Schedule version history"
        sub="Immutable inputs, solver settings, assignments and approval records."
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Version</th>
                <th>Reason</th>
                <th>Created</th>
                <th>Created by</th>
                <th>Approval</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => (
                <tr key={v.id}>
                  <td>
                    <strong>v{v.id}</strong>
                    {data.active_version === v.id && (
                      <span className="cell-sub green-text">Active</span>
                    )}
                  </td>
                  <td>{v.reason}</td>
                  <td>{fmt(v.created_at, true)}</td>
                  <td>{v.created_by}</td>
                  <td>
                    {v.approved_by || v.decision_status || "Pending review"}
                  </td>
                  <td>
                    <button
                      className="text-button"
                      onClick={() =>
                        run("Loading schedule version", async () => {
                          const r = await api(`/versions/${v.id}`);
                          setProposal(r);
                        })
                      }
                    >
                      Compare <ArrowUpRight size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      {confirm && (
        <Modal
          title={"Activate schedule v" + proposal?.id + "?"}
          close={() => setConfirm(false)}
        >
          <div className="detail-body">
            <p>
              This replaces the active production plan and applies the factory
              inputs saved with this proposal.
            </p>
            <p>
              <strong>
                {impacts.filter((i) => i.newly_at_risk).length} existing
                commitments worsen.
              </strong>{" "}
              Review the impact table before continuing.
            </p>
            <div className="button-row">
              <button className="secondary" onClick={() => setConfirm(false)}>
                Keep current plan
              </button>
              <button
                className="primary"
                disabled={busy}
                onClick={() =>
                  run("Activating approved plan", async () => {
                    await post(`/versions/${proposal?.id}/activate`);
                    setConfirm(false);
                    await refresh();
                    notice(
                      "Schedule activated. Approval and changes are recorded in the audit trail.",
                    );
                  })
                }
              >
                Approve & activate v{proposal?.id}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
