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
  const topRisks = executive?.top_risks ?? [];
  const criticalRisks = kpis?.critical_risks ?? 0;
  const shortestDaysToLineStop = shortestDays(topRisks);
  const dataFreshnessLabel = executive?.automated_data_freshness?.data_freshness_status
    ?? executive?.stock_freshness.freshness_label
    ?? "unknown";

  return (
    <main className="min-w-0">
      <div className="flex min-w-0 flex-col gap-6">
        <section className="overflow-hidden rounded-2xl border bg-card/85 shadow-panel backdrop-blur">
          <div className="flex flex-col gap-5 px-6 py-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
            <div className="max-w-3xl space-y-3">
              <Badge variant="outline">Inbound Control Tower</Badge>
              <div className="space-y-2">
                <h1 className="max-w-4xl text-2xl font-semibold tracking-tight sm:text-3xl">
                  Executive view of continuity risk, actions, and pilot readiness.
                </h1>
                <p className="text-sm text-mutedForeground">
                  Leadership snapshot of where risk exists, what is being done, and what needs attention next.
                </p>
              </div>
            </div>
            <div className="shrink-0 rounded-2xl bg-primary px-5 py-4 text-primaryForeground shadow-panel">
              <p className="text-xs uppercase tracking-[0.22em] text-primaryForeground/70">
                Active tenant
              </p>
              <p className="mt-2 text-xl font-semibold">
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

        {criticalRisks > 0 ? (
          <section className="rounded-2xl border border-red-300 bg-red-50 px-5 py-3 text-red-950 shadow-panel">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="rounded-xl bg-red-600 p-2.5 text-white">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-lg font-semibold">Plant continuity risk active</h2>
                <p className="mt-1 text-sm text-red-900">
                  {criticalRisks} critical materials may stop operations within threshold.
                </p>
              </div>
            </div>
          </section>
        ) : null}

        <section className="grid min-w-0 gap-4 md:grid-cols-2 xl:grid-cols-5">
          {[
            { label: "Critical risks", value: String(kpis?.critical_risks ?? 0), trend: "immediate continuity threat" },
            { label: "Warning risks", value: String(kpis?.warning_risks ?? 0), trend: "requires active monitoring" },
            {
              label: "Critical value at risk",
              value: displayCurrency(kpis?.total_estimated_value_at_risk ?? "0"),
              trend: "impact across critical items",
            },
            {
              label: "Shortest days to line stop",
              value: displayDays(shortestDaysToLineStop),
              trend: "based only on available stock",
            },
            {
              label: "Data freshness",
              value: dataFreshnessLabel,
              trend: executive?.automated_data_freshness
                ? `age ${executive.automated_data_freshness.data_freshness_age_minutes ?? "unknown"} min`
                : "stock snapshot status",
            },
          ].map((metric, index) => {
            const Icon = icons[index % icons.length];
            return (
              <Card key={metric.label} className="relative min-w-0 overflow-hidden rounded-2xl bg-card/90 shadow-panel">
                <CardHeader className="min-w-0 space-y-3 px-4 pb-2 pt-4">
                  <div className="absolute right-4 top-4 rounded-xl bg-muted p-2.5 text-primary">
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 pr-12">
                    <CardTitle className="text-sm font-medium leading-snug text-mutedForeground">
                      {metric.label}
                    </CardTitle>
                    <p className="mt-2 break-words text-2xl font-semibold leading-tight tracking-tight">{metric.value}</p>
                  </div>
                </CardHeader>
                <CardContent className="px-4 pb-4">
                  <p className="break-words text-sm leading-snug text-mutedForeground">{metric.trend}</p>
                </CardContent>
              </Card>
            );
          })}
        </section>

        <section className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(280px,0.8fr)]">
          <Card className="min-w-0 bg-card/90 shadow-panel">
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
                Highest-priority plant/material continuity risks using available stock only.
              </p>
              <div className="mt-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
                Blocked or in-transit inventory is not counted as usable cover until available.
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {topRisks.map((row) => (
                  <div
                    key={`${row.plant_id}-${row.material_id}`}
                    className="min-w-0 rounded-2xl border bg-card p-4"
                  >
                    <div className="flex min-w-0 flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                      <div className="min-w-0">
                        <Link
                          href={`/dashboard/stock-cover/${row.plant_id}/${row.material_id}`}
                          className="break-words text-base font-semibold text-primary hover:underline"
                        >
                          {row.material_name}
                        </Link>
                        <p className="mt-1 break-words text-sm text-mutedForeground">{row.plant_name}</p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge status={row.status} />
                        <Badge variant="outline">{rootCauseFor(row)}</Badge>
                      </div>
                    </div>
                    <div className="mt-4 grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      <RiskMetric
                        label="Available stock"
                        value={displayTonnes(row.usable_stock_mt)}
                        helper="usable now"
                        prominent
                      />
                      <RiskMetric label="Blocked stock" value={displayTonnes(row.blocked_stock_mt)} />
                      <RiskMetric
                        label="In-transit"
                        value={displayTonnes(row.raw_inbound_pipeline_mt)}
                        helper={`next ${formatDate(row.next_inbound_eta)}`}
                      />
                      <RiskMetric
                        label="Line stop"
                        value={displayDays(row.days_of_cover)}
                        helper={`threshold ${displayDays(row.threshold_days)}`}
                      />
                    </div>
                    <div className="mt-4 grid min-w-0 gap-3 border-t pt-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,0.85fr)]">
                      <DecisionField label="Why" value={rootCauseFor(row)} />
                      <DecisionField label="Action" value={actionFor(row)} />
                      <div className="min-w-0">
                        <p className="text-xs uppercase tracking-[0.18em] text-mutedForeground">Value at risk</p>
                        <p className="mt-1 font-semibold text-foreground">
                          {displayCurrency(row.estimated_value_at_risk)}
                        </p>
                        <p className="mt-1 break-words text-xs text-mutedForeground">
                          {displayTonnes(row.estimated_production_exposure_mt)} exposed · {formatAssumptionLine(row.value_per_mt_used, row.criticality_multiplier_used)}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
                {topRisks.length === 0 ? (
                  <div className="rounded-2xl border bg-card px-4 py-8 text-center text-sm text-mutedForeground">
                    {stockSummary && stockSummary.total_combinations > 0
                      ? `${stockSummary.total_combinations} plant/material combinations loaded. All are currently safe, so no warning or critical risks are flagged.`
                      : "No warning or critical combinations are currently flagged."}
                  </div>
                ) : null}
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

function RiskMetric({
  label,
  value,
  helper,
  prominent = false,
}: {
  label: string;
  value: string;
  helper?: string;
  prominent?: boolean;
}) {
  return (
    <div className="min-w-0 rounded-xl bg-muted px-3 py-3">
      <p className="text-xs uppercase tracking-[0.16em] text-mutedForeground">{label}</p>
      <p className={`mt-1 break-words font-semibold ${prominent ? "text-lg text-foreground" : "text-foreground"}`}>
        {value}
      </p>
      {helper ? <p className="mt-1 break-words text-xs text-mutedForeground">{helper}</p> : null}
    </div>
  );
}

function DecisionField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs uppercase tracking-[0.18em] text-mutedForeground">{label}</p>
      <p className="mt-1 break-words font-medium text-foreground">{value}</p>
    </div>
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
        source_type?: string | null;
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
            {summary.last_sync_summary.source_type === "microsoft_graph" ? (
              <div className="rounded-xl bg-muted px-4 py-3 text-mutedForeground">
                Microsoft Graph sync recalculates stock risk and value at risk live. Delta counters are shown for legacy URL sync sources only.
              </div>
            ) : (
              <div className="rounded-xl bg-muted px-4 py-3 text-mutedForeground">
                <p>+{summary.last_sync_summary.new_critical_risks_count} new critical risks</p>
                <p>-{summary.last_sync_summary.resolved_risks_count} risks resolved</p>
                <p>{summary.last_sync_summary.newly_breached_actions_count} actions now breached</p>
              </div>
            )}
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
      ? "border-red-300 bg-red-50 text-red-700"
      : status === "warning"
        ? "border-amber-300 bg-amber-50 text-amber-700"
        : status === "insufficient_data"
          ? "border bg-card text-mutedForeground"
          : "border-green-300 bg-green-50 text-green-700";
  const label = status === "safe" ? "healthy" : status.replace("_", " ");
  return <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${className}`}>{label}</span>;
}

function shortestDays(
  rows: Array<{ days_of_cover: string | null; status: string }>,
) {
  const days = rows
    .filter((row) => row.status === "critical" || row.status === "warning")
    .map((row) => parseNumeric(row.days_of_cover))
    .filter((value): value is number => value !== null);
  if (days.length === 0) {
    return null;
  }
  return String(Math.min(...days));
}

function rootCauseFor(row: {
  usable_stock_mt: string | null;
  blocked_stock_mt: string | null;
  raw_inbound_pipeline_mt: string;
  days_of_cover: string | null;
  threshold_days: string | null;
  next_inbound_eta: string | null;
}) {
  const available = parseNumeric(row.usable_stock_mt) ?? 0;
  const blocked = parseNumeric(row.blocked_stock_mt) ?? 0;
  const days = parseNumeric(row.days_of_cover);
  const threshold = parseNumeric(row.threshold_days);
  const nextEta = row.next_inbound_eta ? new Date(row.next_inbound_eta) : null;
  const lineStopDate = days !== null ? new Date(Date.now() + days * 24 * 60 * 60 * 1000) : null;

  if (available <= 0) {
    return "No usable stock";
  }
  if (blocked > available) {
    return "Blocked inventory";
  }
  if (nextEta && lineStopDate && nextEta > lineStopDate) {
    return "Inbound too late";
  }
  if (threshold !== null && days !== null && days <= threshold) {
    return "Below critical cover";
  }
  return "Monitor cover";
}

function actionFor(row: {
  usable_stock_mt: string | null;
  blocked_stock_mt: string | null;
  raw_inbound_pipeline_mt: string;
  days_of_cover: string | null;
  threshold_days: string | null;
  next_inbound_eta: string | null;
}) {
  const cause = rootCauseFor(row);
  if (cause === "Blocked inventory") {
    return "Release blocked stock";
  }
  if (cause === "Inbound too late") {
    return "Expedite inbound shipment";
  }
  if (cause === "Below critical cover") {
    return "Expedite inbound shipment";
  }
  if (cause === "No usable stock") {
    const blocked = parseNumeric(row.blocked_stock_mt) ?? 0;
    const inbound = parseNumeric(row.raw_inbound_pipeline_mt) ?? 0;
    if (blocked > 0) {
      return "Release blocked stock";
    }
    if (inbound > 0) {
      return "Expedite inbound shipment";
    }
    return "Activate alternate supplier";
  }
  return "Substitute material if allowed";
}

function displayTonnes(value: string | null) {
  if (!value) {
    return "—";
  }
  return `${Number(value).toLocaleString()} MT`;
}

function parseNumeric(value: string | null) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
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
    timeZone: "Asia/Kolkata",
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
