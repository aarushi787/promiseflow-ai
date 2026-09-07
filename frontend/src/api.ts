export type Row = Record<string, any>;
export type Data = {
  factory: Record<string, any>;
  revision: number;
  active_version: number | null;
  plan: Row | null;
  approved_factory?: Row | null;
  pending_master_changes?: boolean;
  readiness?: Row;
  execution_pending_orders?: string[];
};
export type Run = (label: string, fn: () => Promise<void>) => Promise<void>;
export const statusClass = (s: string) =>
  ["ON TIME", "FEASIBLE", "AVAILABLE", "OPTIMAL"].includes(s)
    ? "green"
    : ["LATE", "NOT FEASIBLE", "UNSCHEDULED", "BREAKDOWN"].includes(s)
      ? "red"
      : ["AT RISK", "High", "Critical"].includes(s)
        ? "amber"
        : "neutral";
export async function api(
  path: string,
  options: RequestInit = {},
): Promise<any> {
  let res: Response;
  try {
    res = await fetch("/api" + path, {
      credentials: "same-origin",
      ...options,
      headers:
        options.body instanceof FormData
          ? options.headers
          : { "Content-Type": "application/json", ...options.headers },
    });
  } catch {
    throw new Error(
      "Cannot reach the planning server. Check your connection and try again.",
    );
  }
  if (res.status === 204) return null;
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error(
      "The planning server is unavailable at this address. Please open the workspace served by the PromiseFlow backend or contact your administrator.",
    );
  }
  let data: any;
  try {
    data = await res.json();
  } catch {
    throw new Error(
      "The planning server returned an invalid response. Please try again.",
    );
  }
  if (!res.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail.map((x: Row) => x.msg).join("; ")
          : "Request failed. Please try again.",
    );
  return data;
}
export const post = async (path: string, body?: any): Promise<any> => {
  const recovery = path.match(/^\/versions\/(\d+)\/recover$/);
  const kind = recovery
    ? "recovery"
    : (
        {
          "/plan": "plan",
          "/promise": "promise",
          "/scenario": "scenario",
        } as Record<string, string>
      )[path];
  if (kind) {
    const queued = await api("/jobs", {
      method: "POST",
      body: JSON.stringify({
        kind,
        payload: body || {},
        version_id: recovery ? Number(recovery[1]) : undefined,
      }),
    });
    for (;;) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      const job = await api(`/jobs/${queued.job_id}`);
      if (job.status === "COMPLETED") return job.result;
      if (["FAILED", "INTERRUPTED", "CANCELLED"].includes(job.status))
        throw new Error(job.error || "Planning request cancelled");
    }
  }
  return api(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
};
export const fmt = (v: string | null | undefined, time = false) =>
  v
    ? new Date(v).toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        ...(time ? { hour: "2-digit", minute: "2-digit" } : {}),
      })
    : "Not scheduled";
export const money = (v: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(v);
export function futureDate(data: Data, days: number, hour = 16) {
  const d = new Date(data.plan?.base || Date.now());
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${String(hour).padStart(2, "0")}:00`;
}
