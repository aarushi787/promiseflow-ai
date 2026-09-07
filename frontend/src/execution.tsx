import { useEffect, useState } from "react";
import { api, post, fmt } from "./api";
import type { Row, Run } from "./api";
import { Badge, Empty, Field, Panel, Modal } from "./ui";

export function ShopFloor({
  role,
  run,
  refresh,
  busy,
}: {
  role: string;
  run: Run;
  refresh: () => Promise<void>;
  busy: boolean;
}) {
  const [data, setData] = useState<Row | null>(null);
  const [error, setError] = useState("");
  const [eventError, setEventError] = useState("");
  const [selected, setSelected] = useState("");
  const [kind, setKind] = useState("START");
  const [quantity, setQuantity] = useState(0);
  const [at, setAt] = useState("");
  const [reason, setReason] = useState("");
  const [correctionReason, setCorrectionReason] = useState("");
  const [confirmation, setConfirmation] = useState(false);
  const [balances, setBalances] = useState<Row[]>([]);
  const [filter, setFilter] = useState("");
  const editable = ["supervisor", "planner", "manager", "admin"].includes(role);
  const manager = ["manager", "admin"].includes(role);
  const load = async () => {
    const d = await api("/execution");
    setData(d);
    setConfirmation(false);
    setBalances(
      d.materials.map((m: Row) => ({
        material_id: m.id,
        stock: m.stock,
        reserved: m.reserved,
        incoming: m.incoming,
        arrival: m.arrival,
      })),
    );
  };
  useEffect(() => {
    let cancelled = false;
    api("/execution")
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setBalances(
          d.materials.map((m: Row) => ({
            material_id: m.id,
            stock: m.stock,
            reserved: m.reserved,
            incoming: m.incoming,
            arrival: m.arrival,
          })),
        );
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  if (error) return <Empty title="Progress could not be loaded" body={error} />;
  if (!data) return <p>Loading production progress…</p>;
  const op = data.operations.find((o: Row) => o.id === selected);
  const lastEvent = [...data.events].reverse().find((e: Row) => !e.correction);
  const choose = (o: Row) => {
    setEventError("");
    setSelected(o.id);
    setKind(
      o.status === "NOT STARTED"
        ? "START"
        : o.status === "RUNNING"
          ? "PROGRESS"
          : "RESUME",
    );
    setQuantity(o.quantity_completed);
    setReason("");
  };
  const actions =
    op?.status === "NOT STARTED"
      ? ["START"]
      : op?.status === "RUNNING"
        ? ["PROGRESS", "PAUSE", "BREAKDOWN", "HOLD", "COMPLETE"]
        : op?.status === "COMPLETE"
          ? []
          : ["RESUME"];
  return (
    <div className="execution-page">
      <Panel
        title="Actual shop-floor progress"
        sub={`Approved schedule ${data.version_id ? `v${data.version_id}` : "not available"} · quantities are cumulative per transfer batch`}
      >
        <p className="execution-note">
          Record events in plant-wide chronological order using plant-local
          time. Actuals preserve the approved schedule and do not change
          cycle-time standards. Partial-work rescheduling is not yet supported.
        </p>
        <div className="execution-form">
          <Field label="Find an order, operation or resource">
            <input
              type="search"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Order number or resource"
            />
          </Field>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Order / operation</th>
                <th>Resource</th>
                <th>Progress</th>
                <th>Planned finish</th>
                <th>Actual finish / variance</th>
                <th>State</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.operations
                .filter((o: Row) =>
                  `${o.id} ${o.resource_id} ${o.operation}`
                    .toLowerCase()
                    .includes(filter.toLowerCase()),
                )
                .map((o: Row) => (
                  <tr key={o.id}>
                    <td>
                      <strong>{o.order_id}</strong>
                      <br />
                      {o.job_id} · {o.operation}
                    </td>
                    <td>{o.resource_id}</td>
                    <td>
                      {o.quantity_completed} / {o.quantity}
                      <br />
                      <small>{o.remaining_quantity} remaining</small>
                    </td>
                    <td>{fmt(o.end, true)}</td>
                    <td>
                      {o.actual_finish ? (
                        <>
                          {fmt(o.actual_finish, true)}
                          <br />
                          {o.finish_variance_minutes > 0 ? "+" : ""}
                          {o.finish_variance_minutes} min
                        </>
                      ) : (
                        "Not finished"
                      )}
                    </td>
                    <td>
                      <Badge value={o.status} />
                    </td>
                    <td>
                      {editable && o.status !== "COMPLETE" && (
                        <button
                          className="btn secondary"
                          onClick={() => choose(o)}
                        >
                          Record
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        {!data.operations.length && (
          <Empty
            title="No approved operations"
            body="Approve a production plan before recording actual work."
          />
        )}
      </Panel>
      {editable && op && actions.length > 0 && (
        <Modal title={`Record ${op.id}`} close={() => setSelected("")}>
          <form
            className="execution-form"
            onSubmit={(e) => {
              e.preventDefault();
              setEventError("");
              run("Recording progress", async () => {
                await post("/execution/events", {
                  request_id: crypto.randomUUID(),
                  revision: data.revision,
                  version_id: data.version_id,
                  operation_id: selected,
                  kind,
                  quantity_completed: quantity,
                  occurred_at: at,
                  reason,
                }).catch((e) => {
                  setEventError(e.message);
                  throw e;
                });
                await load();
                await refresh();
                setSelected("");
              });
            }}
          >
            {eventError && (
              <div role="alert" className="execution-event-error">
                <p>{eventError}</p>
                <button
                  type="button"
                  className="btn secondary"
                  onClick={() =>
                    run("Refreshing progress", async () => {
                      await load();
                      await refresh();
                      setSelected("");
                    })
                  }
                >
                  Reload progress
                </button>
              </div>
            )}
            <Field label="Event">
              <select
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value);
                  setQuantity(
                    e.target.value === "COMPLETE"
                      ? op.quantity
                      : op.quantity_completed,
                  );
                }}
              >
                {actions.map((a) => (
                  <option key={a}>{a}</option>
                ))}
              </select>
            </Field>
            <Field label="Occurred at · plant-local">
              <input
                required
                type="datetime-local"
                value={at}
                onChange={(e) => setAt(e.target.value)}
              />
            </Field>
            <Field label="Total good quantity completed">
              <input
                type="number"
                min={0}
                max={op.quantity}
                required
                value={quantity}
                disabled={!["PROGRESS", "COMPLETE"].includes(kind)}
                onChange={(e) => setQuantity(Number(e.target.value))}
              />
            </Field>
            <Field label="Reason / observation">
              <input
                required
                minLength={5}
                maxLength={1000}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </Field>
            <button
              className="btn primary"
              disabled={busy || (op.status === "HOLD" && !manager)}
            >
              Save actual event
            </button>
            {op.status === "HOLD" && !manager && (
              <p>A manager must release held work.</p>
            )}
          </form>
        </Modal>
      )}
      {!!data.pending_orders.length && (
        <Panel
          title="Reconcile observed production"
          sub={`Orders: ${data.pending_orders.join(", ")}`}
        >
          <p className="execution-note">
            Planning is paused until every operation of these orders is
            complete. A manager then confirms current material balances, closes
            the orders and rebuilds the remaining plan. Balances must already
            account for consumption and receipts; no automatic stock deduction
            is added.
          </p>
          {!data.can_reconcile && (
            <p>Finish the remaining batch operations before reconciliation.</p>
          )}
          {data.can_reconcile && manager && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                run("Reconciling production", async () => {
                  await post("/execution/reconcile", {
                    revision: data.revision,
                    balances,
                    reason,
                  });
                  await load();
                  await refresh();
                  setReason("");
                });
              }}
            >
              {balances.map((b, i) => (
                <div className="execution-form" key={b.material_id}>
                  <strong>{b.material_id}</strong>
                  {["stock", "reserved", "incoming"].map((key) => (
                    <Field key={key} label={key}>
                      <input
                        type="number"
                        min={0}
                        step="any"
                        required
                        value={b[key]}
                        onChange={(e) =>
                          setBalances((bs) =>
                            bs.map((v, j) =>
                              i === j
                                ? { ...v, [key]: Number(e.target.value) }
                                : v,
                            ),
                          )
                        }
                      />
                    </Field>
                  ))}
                  <Field label="Incoming ETA">
                    <input
                      type="datetime-local"
                      value={b.arrival?.slice(0, 16) || ""}
                      onChange={(e) =>
                        setBalances((bs) =>
                          bs.map((v, j) =>
                            i === j
                              ? { ...v, arrival: e.target.value || null }
                              : v,
                          ),
                        )
                      }
                    />
                  </Field>
                </div>
              ))}
              <Field label="Reconciliation reason">
                <input
                  required
                  minLength={5}
                  maxLength={1000}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </Field>
              <label className="execution-confirm">
                <input
                  type="checkbox"
                  required
                  checked={confirmation}
                  onChange={(e) => setConfirmation(e.target.checked)}
                />
                I verified these balances after consumption and receipts. Close
                the listed orders as completed.
              </label>
              <button className="btn primary" disabled={busy || !confirmation}>
                Confirm balances and close orders
              </button>
            </form>
          )}
          {data.can_reconcile && !manager && (
            <p>A manager or administrator must confirm reconciliation.</p>
          )}
        </Panel>
      )}
      <Panel
        title="Production event history"
        sub="Observed time and recorded time are retained separately."
      >
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Operation</th>
                <th>Event</th>
                <th>Observed · plant-local</th>
                <th>Recorded</th>
                <th>Good quantity</th>
                <th>By / reason</th>
              </tr>
            </thead>
            <tbody>
              {[...data.events].reverse().map((e: Row) => (
                <tr key={e.id}>
                  <td>{e.body.operation_id}</td>
                  <td>
                    {e.body.kind}
                    {e.correction && (
                      <>
                        <br />
                        <strong>VOIDED</strong>
                      </>
                    )}
                  </td>
                  <td>{fmt(e.body.occurred_at, true)}</td>
                  <td>{fmt(e.recorded_at, true)}</td>
                  <td>{e.body.quantity_completed}</td>
                  <td>
                    {e.actor}
                    <br />
                    {e.body.reason}
                    {e.correction && (
                      <>
                        <br />
                        Voided by {e.correction.actor}: {e.correction.reason}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!data.events.length && (
          <p className="execution-note">
            No actual production has been recorded.
          </p>
        )}
        {manager &&
          lastEvent &&
          data.pending_orders.includes(lastEvent.order_id) && (
            <form
              className="execution-form"
              onSubmit={(e) => {
                e.preventDefault();
                run("Correcting latest event", async () => {
                  await post(`/execution/events/${lastEvent.id}/void`, {
                    revision: data.revision,
                    reason: correctionReason,
                  });
                  await load();
                  await refresh();
                  setSelected("");
                  setCorrectionReason("");
                });
              }}
            >
              <Field
                label={`Correction reason · ${lastEvent.body.operation_id} / ${lastEvent.body.kind}`}
              >
                <input
                  required
                  minLength={5}
                  maxLength={1000}
                  value={correctionReason}
                  onChange={(e) => setCorrectionReason(e.target.value)}
                />
              </Field>
              <button className="btn secondary" disabled={busy}>
                Void latest mistaken event
              </button>
            </form>
          )}
      </Panel>
    </div>
  );
}
