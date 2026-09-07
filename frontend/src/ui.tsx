import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Package, X, ArrowUpRight } from "@phosphor-icons/react";
import { fmt, statusClass } from "./api";
import type { Data, Row } from "./api";
export function Badge({ value }: { value: string }) {
  return (
    <span className={"badge " + statusClass(value)}>
      <span />
      {value.toLowerCase().replaceAll("_", " ")}
    </span>
  );
}
export function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty">
      <Package size={30} />
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}
export function Panel({
  title,
  sub,
  action,
  children,
  className = "",
}: {
  title: string;
  sub?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={"panel " + className}>
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {sub && <p>{sub}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  useEffect(() => {
    const before = document.activeElement as HTMLElement;
    const fn = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "Tab") {
        const els = Array.from(
          document.querySelectorAll<HTMLElement>(
            ".modal button,.modal input,.modal select,.modal textarea,.modal a",
          ),
        ).filter((x) => !x.hasAttribute("disabled"));
        const first = els[0],
          last = els.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", fn);
    document.querySelector<HTMLElement>(".modal button")?.focus();
    return () => {
      document.removeEventListener("keydown", fn);
      before?.focus();
    };
  }, [close]);
  return (
    <div className="overlay" onClick={close}>
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="panel-heading">
          <h2>{title}</h2>
          <button
            className="icon-button"
            onClick={close}
            aria-label="Close dialog"
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function JsonEditor({
  title,
  value,
  onSave,
  close,
}: {
  title: string;
  value: Row;
  onSave: (v: Row) => void;
  close: () => void;
}) {
  const [text, setText] = useState(JSON.stringify(value, null, 2)),
    [error, setError] = useState("");
  return (
    <Modal title={title} close={close}>
      <div className="detail-body">
        <p className="fine-print">
          Advanced master editor. References and manufacturing rules are
          validated before saving. Use Excel Imports for bulk onboarding.
        </p>
        <textarea
          className="json-editor"
          aria-label="Master record JSON"
          value={text}
          onChange={(e) => setText(e.target.value)}
          spellCheck={false}
        />
        {error && <p className="red-text">{error}</p>}
        <button
          className="primary"
          onClick={() => {
            try {
              onSave(JSON.parse(text));
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          Validate & save
        </button>
      </div>
    </Modal>
  );
}
export function OrderFields({
  data,
  value,
  onChange,
}: {
  data: Data;
  value: Row;
  onChange: (r: Row) => void;
}) {
  const f = data.factory;
  const set = (k: string, v: any) => onChange({ ...value, [k]: v });
  return (
    <div className="form-grid">
      <Field label="Order number">
        <input
          required
          value={value.id}
          onChange={(e) => set("id", e.target.value)}
        />
      </Field>
      <Field label="Customer">
        <select
          required
          value={value.customer_id}
          onChange={(e) => set("customer_id", e.target.value)}
        >
          {f.customers.map((c: Row) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Product">
        <select
          required
          value={value.product_id}
          onChange={(e) => set("product_id", e.target.value)}
        >
          {f.products.map((p: Row) => (
            <option key={p.id} value={p.id}>
              {p.id} · {p.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Quantity (pieces)">
        <input
          required
          type="number"
          min="1"
          max="1000000"
          value={value.quantity}
          onChange={(e) => set("quantity", Number(e.target.value))}
        />
      </Field>
      <Field label="Requested delivery">
        <input
          required
          type="datetime-local"
          value={value.requested_date?.slice(0, 16)}
          onChange={(e) => set("requested_date", e.target.value)}
        />
      </Field>
      <Field label="Priority">
        <select
          value={value.priority}
          onChange={(e) => set("priority", e.target.value)}
        >
          {["Critical", "High", "Normal", "Low"].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
      </Field>
    </div>
  );
}
export function OrderTable({
  data,
  rows,
  inspect,
}: {
  data: Data;
  rows: Row[];
  inspect: (id: string) => void;
}) {
  const f = data.approved_factory || data.factory;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Order / customer</th>
            <th>Product</th>
            <th>Quantity</th>
            <th>Promised date</th>
            <th>Projected dispatch</th>
            <th>Delivery status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((o) => {
            const src = f.orders.find((x: Row) => x.id === o.id);
            return (
              <tr key={o.id}>
                <td>
                  <button className="order-link" onClick={() => inspect(o.id)}>
                    {o.id}
                  </button>
                  <span className="cell-sub">
                    {f.customers.find((c: Row) => c.id === src?.customer_id)
                      ?.name || "Proposed order"}
                  </span>
                </td>
                <td>
                  {src?.product_id}
                  <span className="cell-sub">
                    {
                      f.products.find((p: Row) => p.id === src?.product_id)
                        ?.name
                    }
                  </span>
                </td>
                <td className="number">
                  {src?.quantity.toLocaleString("en-IN")}
                  <span className="cell-sub">pieces</span>
                </td>
                <td>{fmt(o.due)}</td>
                <td>
                  {fmt(o.completion)}
                  {o.tardiness_minutes ? (
                    <span className="cell-sub red-text">
                      +{(o.tardiness_minutes / 1440).toFixed(1)} days
                    </span>
                  ) : null}
                </td>
                <td>
                  <Badge value={o.status} />
                </td>
                <td>
                  <button
                    className="icon-button"
                    onClick={() => inspect(o.id)}
                    aria-label={"Explain " + o.id}
                  >
                    <ArrowUpRight size={17} />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!rows.length && (
        <Empty
          title="No matching orders"
          body="Add an order or change your filters."
        />
      )}
    </div>
  );
}
