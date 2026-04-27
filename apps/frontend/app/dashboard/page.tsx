import Link from "next/link";
import { redirect } from "next/navigation";
import { AlertTriangle, Boxes, ShieldAlert, TimerReset } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LineStopForm } from "@/components/line-stops/line-stop-form";
import { getCurrentUser, getExecutiveDashboard, getStockCoverSummary } from "@/lib/api";
import { canManageOperationalWorkflow } from "@/lib/roles";

export const dynamic = "force-dynamic";

const icons = [Boxes, ShieldAlert, AlertTriangle, TimerReset];

export default async function DashboardPage() {
  const [executive, user, stockSummary] = await Promise.all([
    getExecutiveDashboard(),
    getCurrentUser(),
    getStockCoverSummary(),
  ]);
  if (user?.is_superadmin) {
    redirect("/dashboard/superadmin");
  }
  const activeTenant = executive?.tenant ?? "demo-steel";
  const kpis = executive?.kpis;
  const role = user?.memberships[0]?.role;
  const canExportStock = canManageOperationalWorkflow(role);
  const canManageOperations = canManageOperationalWorkflow(role);
  const lineStopOptions = dedupeComboOptions(stockSummary?.rows ?? []);

  return (
    <main>
      <div className="flex flex-col gap-8">
        <section className="overflow-hidden rounded-3xl border bg-card/85 shadow-panel backdrop-blur">
          <div className="flex flex-col gap-6 px-6 py-8 lg:flex-row lg:items-end lg:justify-between lg:px-10">
            <div className="max-w-2xl space-y-4">
              <Badge variant="outline">Inbound Control Tower</Badge>
              <div className="space-y-2">
                <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                  Executive view of continuity risk, actions, and pilot readiness.
                </h1>
                <p className="text-sm text-mutedForeground sm:text-base">
                  Leadership snapshot of where risk exists, what is being done, and what needs attention next.
                </p>
              </div>
            </div>
            <div className="rounded-2xl bg-primary px-5 py-4 text-primaryForeground shadow-panel">
              <p className="text-xs uppercase tracking-[0.22em] text-primaryForeground/70">
                Active tenant
              </p>
              <p className="mt-2 text-2xl font-semibold">
                {activeTenant}
              </p>
              <a
                href="/api/exports/executive"
                className="mt-3 inline-flex rounded-2xl border border-primaryForeground/20 px-3 py-2 text-xs font-semibold text-primaryForeground"
              >
                Export executive CSV
              </a>
            </div>
          </div>
        </section>

        {!executive ? (
          <Card className="bg-card/90 shadow-panel">
            <CardHeader>
              <CardTitle>Executive dashboard unavailable</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-mutedForeground">
              The leadership snapshot could not be loaded. Confirm you are signed in to the correct tenant and try again.
            </CardContent>
          </Card>
        ) : null}

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "Tracked combinations", value: String(kpis?.tracked_combinations ?? 0), trend: "plant/material scope" },
            { label: "Critical risks", value: String(kpis?.critical_risks ?? 0), trend: "immediate continuity threat" },
            { label: "Warning risks", value: String(kpis?.warning_risks ?? 0), trend: "requires active monitoring" },
            { label: "Open exceptions", value: String(kpis?.open_exceptions ?? 0), trend: `${kpis?.unassigned_exceptions ?? 0} unassigned` },
            {
              label: "Critical value at risk",
              value: displayCurrency(kpis?.total_estimated_value_at_risk ?? "0"),
              trend: "estimated impact across critical items",
            },
          ].map((metric, index) => {
            const Icon = icons[index % icons.length];
            return (
              <Card key={metric.label} className="bg-card/90 shadow-panel">
                <CardHeader className="flex flex-row items-start justify-between space-y-0">
                  <div>
                    <CardTitle className="text-sm font-medium text-mutedForeground">
                      {metric.label}
                    </CardTitle>
                    <p className="mt-3 text-3xl font-semibold tracking-tight">{metric.value}</p>
                  </div>
                  <div className="rounded-xl bg-muted p-3 text-primary">
                    <Icon className="h-5 w-5" />
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-mutedForeground">{metric.trend}</p>
                </CardContent>
              </Card>
            );
          })}
        </section>

        <section className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
          <Card className="bg-card/90 shadow-panel">
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle>Top at-risk combinations</CardTitle>
                {canExportStock ? (
                  <a
                    href="/api/exports/stock-cover"
                    className="rounded-2xl border px-4 py-2 text-xs font-semibold"
                  >
                    Export stock CSV
                  </a>
                ) : null}
              </div>
              <p className="text-sm text-mutedForeground">
                Highest-priority plant/material continuity risks using refined effective inbound protection.
              </p>
            </CardHeader>
            <CardContent>
              <div className="overflow-hidden rounded-2xl border">
                <table className="w-full text-left text-sm">
                  <thead className="bg-muted text-mutedForeground">
                    <tr>
                      <th className="px-4 py-3 font-medium">Plant</th>
                      <th className="px-4 py-3 font-medium">Material</th>
                      <th className="px-4 py-3 font-medium">Cover</th>
                      <th className="px-4 py-3 font-medium">Days of cover</th>
                      <th className="px-4 py-3 font-medium">Threshold</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="px-4 py-3 font-medium">Impact</th>
                      <th className="px-4 py-3 font-medium">Confidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(executive?.top_risks ?? []).map((row) => (
                      <tr key={`${row.plant_id}-${row.material_id}`} className="border-t bg-card">
                        <td className="px-4 py-3 font-medium">
                          <Link
                            href={`/dashboard/stock-cover/${row.plant_id}/${row.material_id}`}
                            className="text-primary hover:underline"
                          >
                            {row.plant_name}
                          </Link>
                        </td>
                        <td className="px-4 py-3">{row.material_name}</td>
                        <td className="px-4 py-3">
                          {displayTonnes(row.effective_inbound_pipeline_mt)} / {displayTonnes(row.raw_inbound_pipeline_mt)}
                        </td>
                        <td className="px-4 py-3">{displayDays(row.days_of_cover)}</td>
                        <td className="px-4 py-3">
                          {displayDays(row.threshold_days)}
                        </td>
                        <td className="px-4 py-3">
                          <div className="space-y-2">
                            <StatusBadge status={row.status} />
                            <Badge variant="outline">{formatUrgency(row.urgency_band)}</Badge>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-mutedForeground">
                          <p className="font-medium text-foreground">
                            {displayCurrency(row.estimated_value_at_risk)}
                          </p>
                          <p>{displayTonnes(row.estimated_production_exposure_mt)} exposed</p>
                          <p className="text-xs text-mutedForeground/80">
                            {formatAssumptionLine(row.value_per_mt_used, row.criticality_multiplier_used)}
                          </p>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant="outline">{row.confidence}</Badge>
                        </td>
                      </tr>
                    ))}
                    {(executive?.top_risks ?? []).length === 0 ? (
                      <tr>
                        <td className="px-4 py-8 text-center text-mutedForeground" colSpan={8}>
                          {stockSummary && stockSummary.total_combinations > 0
                            ? `${stockSummary.total_combinations} plant/material combinations loaded. All are currently safe, so no warning or critical risks are flagged.`
                            : "No warning or critical combinations are currently flagged."}
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
              {(executive?.top_risks ?? []).length === 0 && (stockSummary?.rows.length ?? 0) > 0 ? (
                <div className="mt-4 rounded-2xl border bg-muted/40 p-4 text-sm">
                  <p className="font-semibold">Uploaded data is loaded</p>
                  <p className="mt-1 text-mutedForeground">
                    Current stock-cover output is safe for the loaded combinations.
                  </p>
                  <div className="mt-3 grid gap-2 md:grid-cols-2">
                    {stockSummary?.rows.slice(0, 4).map((row) => (
                      <Link
                        key={`${row.plant_id}-${row.material_id}`}
                        href={`/dashboard/stock-cover/${row.plant_id}/${row.material_id}`}
                        className="rounded-xl border bg-card px-4 py-3 hover:border-primary"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-medium">{row.material_name}</span>
                          <StatusBadge status={row.calculation.status} />
                        </div>
                        <p className="mt-1 text-mutedForeground">
                          {row.plant_name} · {displayDays(row.calculation.days_of_cover)} cover
                        </p>
                      </Link>
                    ))}
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <div className="grid gap-5">
            <AutomatedFreshnessCard summary={executive?.automated_data_freshness ?? null} />
            <FreshnessCard
              title="Data freshness"
              items={[
                ["Stock", executive?.stock_freshness.freshness_label ?? "unknown", executive?.stock_freshness.last_updated_at ?? null],
                ["Exceptions", executive?.exception_freshness.freshness_label ?? "unknown", executive?.exception_freshness.last_updated_at ?? null],
                ["Movement", executive?.movement_freshness.freshness_label ?? "unknown", executive?.movement_freshness.last_updated_at ?? null],
              ]}
            />
            <AttentionCard items={executive?.needs_attention ?? []} />
          </div>
        </section>

        <section className="grid gap-5 xl:grid-cols-3">
          <ExceptionCard
            title="Critical open exceptions"
            items={executive?.critical_open_exceptions ?? []}
            exportHref="/api/exports/exceptions?status=open&severity=critical"
          />
          <ExceptionCard
            title="Unassigned exceptions"
            items={executive?.unassigned_exceptions ?? []}
          />
          <ExceptionCard
            title="Recently updated exceptions"
            items={executive?.recently_updated_exceptions ?? []}
          />
        </section>

        <section className="grid gap-5 xl:grid-cols-3">
          <MovementCard
            title="Stale movement data"
            items={executive?.stale_movement_shipments ?? []}
          />
          <MovementCard
            title="Low confidence shipments"
            items={executive?.low_confidence_shipments ?? []}
          />
          <MovementCard
            title="Likely delayed shipments"
            items={executive?.likely_delayed_shipments ?? []}
          />
        </section>

        <section className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="grid gap-5">
            <SupplierPerformanceCard items={executive?.supplier_performance ?? []} />
            <SupplierMasterSummaryCard summary={executive?.supplier_performance_summary ?? null} />
          </div>
          <Card className="bg-card/90 shadow-panel">
            <CardHeader>
              <CardTitle>Line stop incident log</CardTitle>
              <p className="text-sm text-mutedForeground">
                Manually capture stoppages so continuity risk can be tied to real production loss over time.
              </p>
            </CardHeader>
            <CardContent>
              {canManageOperations ? (
                <LineStopForm options={lineStopOptions} />
              ) : (
                <p className="text-sm text-mutedForeground">Operator access is required to record incidents.</p>
              )}
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}

function SupplierPerformanceCard({
  items,
}: {
  items: Array<{
    supplier_name: string;
    total_shipments: number;
    on_time_shipments: number;
    on_time_reliability_pct: string;
    active_shipments: number;
    active_shipments_with_risk_signal: number;
    risk_signal_pct: string;
  }>;
}) {
  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <CardTitle>Supplier reliability and risk</CardTitle>
        <p className="text-sm text-mutedForeground">
          On-time reliability uses ETA within 24 hours of plan. Risk score counts active shipments with stale, low-confidence, port-delay, or inland-delay signals.
        </p>
      </CardHeader>
      <CardContent>
        <div className="overflow-hidden rounded-2xl border">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted text-mutedForeground">
              <tr>
                <th className="px-4 py-3 font-medium">Supplier</th>
                <th className="px-4 py-3 font-medium">On-time</th>
                <th className="px-4 py-3 font-medium">Risk signal</th>
                <th className="px-4 py-3 font-medium">Active shipments</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.supplier_name} className="border-t bg-card">
                  <td className="px-4 py-3 font-medium">{item.supplier_name}</td>
                  <td className="px-4 py-3">
                    {displayPercent(item.on_time_reliability_pct)}
                    <p className="text-xs text-mutedForeground">
                      {item.on_time_shipments}/{item.total_shipments} shipments
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    {displayPercent(item.risk_signal_pct)}
                    <p className="text-xs text-mutedForeground">
                      {item.active_shipments_with_risk_signal}/{item.active_shipments} active
                    </p>
                  </td>
                  <td className="px-4 py-3">{item.active_shipments}</td>
                </tr>
              ))}
              {items.length === 0 ? (
                <tr>
                  <td className="px-4 py-8 text-center text-mutedForeground" colSpan={4}>
                    No supplier performance data is available yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function SupplierMasterSummaryCard({
  summary,
}: {
  summary: {
    top_suppliers: Array<{
      supplier_id: string;
      supplier_name: string;
      reliability_grade: string;
      on_time_reliability_pct: string;
      risk_signal_pct: string;
      active_shipments: number;
    }>;
    bottom_suppliers: Array<{
      supplier_id: string;
      supplier_name: string;
      reliability_grade: string;
      on_time_reliability_pct: string;
      risk_signal_pct: string;
      active_shipments: number;
    }>;
    grade_d_count: number;
    high_risk_supplier_count: number;
  } | null;
}) {
  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle>Supplier master summary</CardTitle>
          <Link href="/dashboard/suppliers" className="rounded-2xl border px-4 py-2 text-xs font-semibold">
            View suppliers
          </Link>
        </div>
        <p className="text-sm text-mutedForeground">
          Best and worst linked supplier records by reliability grade and risk signal load.
        </p>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        {!summary ? (
          <p className="text-sm text-mutedForeground md:col-span-2">Supplier master data is not available yet.</p>
        ) : (
          <>
            <div className="rounded-2xl border bg-card p-4">
              <p className="text-sm font-semibold">Best suppliers</p>
              <div className="mt-3 space-y-3">
                {summary.top_suppliers.map((item) => (
                  <SupplierSummaryRow key={item.supplier_id} item={item} />
                ))}
                {summary.top_suppliers.length === 0 ? <p className="text-sm text-mutedForeground">No linked suppliers yet.</p> : null}
              </div>
            </div>
            <div className="rounded-2xl border bg-card p-4">
              <p className="text-sm font-semibold">Worst suppliers</p>
              <div className="mt-3 space-y-3">
                {summary.bottom_suppliers.map((item) => (
                  <SupplierSummaryRow key={item.supplier_id} item={item} />
                ))}
                {summary.bottom_suppliers.length === 0 ? <p className="text-sm text-mutedForeground">No linked suppliers yet.</p> : null}
              </div>
            </div>
            <div className="rounded-2xl bg-muted px-4 py-3 text-sm text-mutedForeground md:col-span-2">
              <p>{summary.grade_d_count} suppliers have grade D reliability.</p>
              <p>{summary.high_risk_supplier_count} suppliers have risk signals on more than 50% of active shipments.</p>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function SupplierSummaryRow({
  item,
}: {
  item: {
    supplier_id: string;
    supplier_name: string;
    reliability_grade: string;
    on_time_reliability_pct: string;
    risk_signal_pct: string;
    active_shipments: number;
  };
}) {
  return (
    <Link href={`/dashboard/suppliers/${item.supplier_id}`} className="block rounded-xl border px-3 py-2 hover:border-primary">
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium">{item.supplier_name}</span>
        <span className="rounded-full border px-2 py-1 text-xs font-semibold">Grade {item.reliability_grade}</span>
      </div>
      <p className="mt-1 text-xs text-mutedForeground">
        {displayPercent(item.on_time_reliability_pct)} on-time · {displayPercent(item.risk_signal_pct)} risk · {item.active_shipments} active
      </p>
    </Link>
  );
}

function AutomatedFreshnessCard({
  summary,
}: {
  summary: {
    last_sync_summary: {
      last_synced_at: string | null;
      last_sync_status: string | null;
      new_critical_risks_count: number;
      resolved_risks_count: number;
      newly_breached_actions_count: number;
    };
    data_freshness_status: string;
    data_freshness_age_minutes: number | null;
  } | null;
}) {
  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <CardTitle>Data freshness + changes</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {!summary ? (
          <p className="text-mutedForeground">No automated data sources are active for this tenant yet.</p>
        ) : (
          <>
            <div className="rounded-xl bg-muted px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <span className="font-medium">Automated sync</span>
                <Badge variant="outline">{summary.data_freshness_status}</Badge>
              </div>
              <p className="mt-2 text-mutedForeground">
                Last sync: {formatDate(summary.last_sync_summary.last_synced_at)}
              </p>
              <p className="text-mutedForeground">
                Status: {summary.last_sync_summary.last_sync_status ?? "not_started"}
              </p>
              <p className="text-mutedForeground">
                Age: {summary.data_freshness_age_minutes !== null ? `${summary.data_freshness_age_minutes} min` : "Not synced yet"}
              </p>
            </div>
            <div className="rounded-xl bg-muted px-4 py-3 text-mutedForeground">
              <p>+{summary.last_sync_summary.new_critical_risks_count} new critical risks</p>
              <p>-{summary.last_sync_summary.resolved_risks_count} risks resolved</p>
              <p>{summary.last_sync_summary.newly_breached_actions_count} actions now breached</p>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function FreshnessCard({ title, items }: { title: string; items: Array<[string, string, string | null]> }) {
  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {items.map(([label, freshness, updatedAt]) => (
          <div key={label} className="rounded-xl bg-muted px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium">{label}</span>
              <Badge variant="outline">{freshness}</Badge>
            </div>
            <p className="mt-2 text-mutedForeground">{formatDate(updatedAt)}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function AttentionCard({ items }: { items: Array<{ description: string; linked_label: string; href: string; current_owner: string | null; recommended_next_step: string; owner_role_recommended: string | null; action_deadline_hours: number | null; action_priority: string | null; action_status: string | null; action_sla_breach: boolean; action_age_hours: string | null }> }) {
  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <CardTitle>What needs attention</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {items.map((item) => (
          <div key={`${item.href}-${item.description}`} className={`rounded-xl border bg-card px-4 py-3 ${item.action_sla_breach ? "border-accent bg-muted" : ""}`}>
            <Link href={item.href} className="font-semibold text-primary hover:underline">
              {item.description}
            </Link>
            <p className="mt-2 text-mutedForeground">{item.linked_label}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge variant="outline">{(item.action_status ?? "pending").replace("_", " ")}</Badge>
              {item.action_sla_breach ? <Badge variant="outline">SLA breached</Badge> : null}
            </div>
            <p className="text-mutedForeground">Owner: {item.current_owner ?? "Unassigned"}</p>
            <p className="text-mutedForeground">Recommended role: {item.owner_role_recommended ?? "tenant_admin"}</p>
            <p className="text-mutedForeground">{formatCountdown(item.action_deadline_hours, item.action_age_hours, item.action_status)}</p>
            <p className="mt-2">{item.recommended_next_step}</p>
          </div>
        ))}
        {items.length === 0 ? <p className="text-mutedForeground">No immediate attention items are currently flagged.</p> : null}
      </CardContent>
    </Card>
  );
}

function ExceptionCard({
  title,
  items,
  exportHref,
}: {
  title: string;
  items: Array<{ id: number; title: string; severity: string; owner_name: string | null; updated_at: string }>;
  exportHref?: string;
}) {
  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle>{title}</CardTitle>
          {exportHref ? (
            <a href={exportHref} className="rounded-2xl border px-4 py-2 text-xs font-semibold">
              Export CSV
            </a>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {items.map((item) => (
          <div key={item.id} className="rounded-xl border bg-card px-4 py-3">
            <Link href={`/dashboard/exceptions/${item.id}`} className="font-semibold text-primary hover:underline">
              {item.title}
            </Link>
            <p className="mt-2 text-mutedForeground">Owner: {item.owner_name ?? "Unassigned"}</p>
            <p className="text-mutedForeground">Updated: {formatDate(item.updated_at)}</p>
          </div>
        ))}
        {items.length === 0 ? <p className="text-mutedForeground">No items in this section.</p> : null}
      </CardContent>
    </Card>
  );
}

function MovementCard({ title, items }: { title: string; items: Array<{ shipment_id: string; plant_name: string; material_name: string; confidence: string; freshness_label: string; issue_label: string }> }) {
  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {items.map((item) => (
          <div key={`${item.shipment_id}-${item.issue_label}`} className="rounded-xl border bg-card px-4 py-3">
            <Link href={`/dashboard/shipments/${item.shipment_id}`} className="font-semibold text-primary hover:underline">
              {item.shipment_id}
            </Link>
            <p className="mt-2 text-mutedForeground">{item.plant_name} / {item.material_name}</p>
            <p className="text-mutedForeground">{item.issue_label}</p>
            <p className="text-mutedForeground">{item.confidence} confidence · {item.freshness_label}</p>
          </div>
        ))}
        {items.length === 0 ? <p className="text-mutedForeground">No items in this section.</p> : null}
      </CardContent>
    </Card>
  );
}

function StatusBadge({ status }: { status: string }) {
  const className =
    status === "critical"
      ? "border-accent bg-muted text-primary"
      : status === "warning"
        ? "border-accent bg-muted text-primary"
        : status === "insufficient_data"
          ? "border bg-card text-mutedForeground"
          : "border-accent bg-muted text-accent";
  return <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${className}`}>{status.replace("_", " ")}</span>;
}

function displayTonnes(value: string | null) {
  if (!value) {
    return "—";
  }
  return `${Number(value).toLocaleString()} MT`;
}

function displayCurrency(value: string | null) {
  const numeric = Number(value ?? "0");
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(numeric);
}

function displayPercent(value: string | null) {
  return `${Number(value ?? "0").toFixed(1)}%`;
}

function formatAssumptionLine(valuePerMt: string | null, multiplier: string | null) {
  if (!valuePerMt || !multiplier) {
    return "Assumptions unavailable";
  }
  return `(Assumes ${displayCurrency(valuePerMt)}/MT x ${trimNumber(multiplier)})`;
}

function trimNumber(value: string) {
  return Number(value).toString();
}

function formatUrgency(value: string) {
  return value.replace("_", " ");
}

function displayDays(value: string | null) {
  if (!value) {
    return "—";
  }
  return `${Number(value).toFixed(2)} d`;
}

function formatDate(value: string | null) {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatDeadline(value: number | null) {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${value}h`;
}

function formatCountdown(deadlineHours: number | null, ageHours: string | null, actionStatus: string | null) {
  if (actionStatus === "completed") {
    return "Completed";
  }
  if (deadlineHours === null || ageHours === null) {
    return "Deadline unavailable";
  }
  const remaining = deadlineHours - Number(ageHours);
  if (remaining >= 0) {
    return `Due in ${Math.ceil(remaining)}h`;
  }
  return `Overdue by ${Math.ceil(Math.abs(remaining))}h`;
}

function dedupeComboOptions(
  rows: Array<{
    plant_id: number;
    plant_name: string;
    material_id: number;
    material_name: string;
  }>,
) {
  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = `${row.plant_id}:${row.material_id}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}
