import Link from "next/link";

import type { CustomerHealthSummary } from "@/lib/api";

const statusTone: Record<string, string> = {
  not_started: "bg-slate-100 text-slate-700 ring-slate-200",
  in_progress: "bg-blue-50 text-blue-700 ring-blue-200",
  blocked: "bg-red-50 text-red-700 ring-red-200",
  ready_for_final_review: "bg-amber-50 text-amber-700 ring-amber-200",
  ready_for_proposal: "bg-emerald-50 text-emerald-700 ring-emerald-200",
};

export function CustomerHealthTable({ items }: { items: CustomerHealthSummary[] }) {
  return (
    <section className="rounded-3xl border bg-card/90 p-6 shadow-panel">
      <div className="mb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-mutedForeground">
          Customer Health
        </p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight">
          Commercial readiness across pilots
        </h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] text-left text-sm">
          <thead className="text-xs uppercase tracking-[0.14em] text-mutedForeground">
            <tr>
              <th className="py-3 pr-4">Tenant</th>
              <th className="py-3 pr-4">Status</th>
              <th className="py-3 pr-4">Progress</th>
              <th className="py-3 pr-4">Latest Review</th>
              <th className="py-3 pr-4">Actions</th>
              <th className="py-3 pr-4">Reports</th>
              <th className="py-3 pr-4">Recommendation</th>
              <th className="py-3">Open</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {items.map((item) => (
              <tr key={item.tenant_id}>
                <td className="py-4 pr-4 font-semibold">{item.tenant_name}</td>
                <td className="py-4 pr-4">
                  <HealthBadge status={item.readiness_status} />
                </td>
                <td className="py-4 pr-4">{item.pilot_progress_percent}%</td>
                <td className="py-4 pr-4">{formatDate(item.latest_review_date)}</td>
                <td className="py-4 pr-4">
                  {item.open_actions_count} open · {item.overdue_actions_count} overdue
                </td>
                <td className="py-4 pr-4">{item.reports_generated_count}</td>
                <td className="max-w-sm py-4 pr-4 text-mutedForeground">
                  {item.recommendation}
                </td>
                <td className="py-4">
                  <Link
                    href={`/dashboard/superadmin/tenants/${item.tenant_id}`}
                    className="rounded-lg border px-3 py-2 text-xs font-semibold"
                  >
                    View Tenant
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function TenantHealthPanel({ health }: { health: CustomerHealthSummary }) {
  return (
    <section className="rounded-3xl border bg-card/90 p-6 shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-mutedForeground">
            Customer Health
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight">
            Commercial readiness
          </h2>
        </div>
        <HealthBadge status={health.readiness_status} />
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-6">
        <Metric label="Progress" value={`${health.pilot_progress_percent}%`} />
        <Metric label="Latest review" value={formatDate(health.latest_review_date)} />
        <Metric label="Open actions" value={health.open_actions_count} />
        <Metric label="Overdue" value={health.overdue_actions_count} />
        <Metric label="Reports" value={health.reports_generated_count} />
        <Metric label="Latest report" value={formatDate(health.latest_report_generated_at)} />
      </div>
      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl bg-slate-50 p-4 lg:col-span-1">
          <p className="text-sm font-semibold">Recommendation</p>
          <p className="mt-2 text-sm leading-6 text-mutedForeground">{health.recommendation}</p>
        </div>
        <ListBlock title="Next best actions" items={health.next_best_actions} />
        <ListBlock
          title={health.blockers.length ? "Blockers" : "Readiness reasons"}
          items={health.blockers.length ? health.blockers : health.readiness_reasons}
        />
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-mutedForeground">
        {label}
      </p>
      <p className="mt-2 text-xl font-semibold text-foreground">{value}</p>
    </div>
  );
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <p className="text-sm font-semibold">{title}</p>
      <ul className="mt-2 grid gap-2 text-sm leading-6 text-mutedForeground">
        {(items.length ? items : ["No items."]).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function HealthBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ring-1 ${
        statusTone[status] ?? statusTone.in_progress
      }`}
    >
      {label(status)}
    </span>
  );
}

function label(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatDate(value: string | null) {
  if (!value) return "None";
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(new Date(value));
}
