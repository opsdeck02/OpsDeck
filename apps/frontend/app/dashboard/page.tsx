import Link from "next/link";
import { redirect } from "next/navigation";
import { AlertTriangle, ArrowRight, Boxes, ShieldAlert, TimerReset } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getCurrentUser, getExecutiveDashboard, getStockCoverSummary } from "@/lib/api";

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
  const topRisks = executive?.top_risks ?? [];
  const criticalRisks = kpis?.critical_risks ?? 0;
  const shortestDaysToLineStop = shortestDays(topRisks);
  const dataFreshnessLabel = executive?.automated_data_freshness?.data_freshness_status
    ?? executive?.stock_freshness.freshness_label
    ?? "unknown";

  return (
    <main className="min-w-0">
      <div className="flex min-w-0 flex-col gap-4">
        <section className="overflow-hidden rounded-2xl border bg-card/85 shadow-panel backdrop-blur">
          <div className="flex flex-col gap-4 px-4 py-5 lg:flex-row lg:items-center lg:justify-between lg:px-5">
            <div className="max-w-3xl space-y-3">
              <Badge variant="outline">Continuity intelligence</Badge>
              <div className="space-y-2">
                <h1 className="max-w-4xl text-2xl font-semibold tracking-tight">
                  Continuity exposure overview
                </h1>
                <p className="text-sm text-mutedForeground">
                  A compact view of exposed materials, inbound movement, and signal trust for the current tenant.
                </p>
              </div>
              <Link
                href="/dashboard/risk-workspace"
                className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primaryForeground"
              >
                Open Risk Workspace
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
            <div className="shrink-0 rounded-2xl bg-primary px-4 py-3 text-primaryForeground shadow-panel">
              <p className="text-xs uppercase tracking-[0.22em] text-primaryForeground/70">
                Active tenant
              </p>
              <p className="mt-1 text-lg font-semibold">
                {activeTenant}
              </p>
            </div>
          </div>
        </section>

        {!executive ? (
          <Card className="bg-card/90 shadow-panel">
            <CardHeader>
              <CardTitle>Continuity overview unavailable</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-mutedForeground">
              The continuity overview could not be loaded. Confirm you are signed in to the correct tenant and try again.
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

        <Card className="bg-card/90 shadow-panel">
          <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-semibold">Open Risk Workspace</p>
              <p className="mt-1 text-sm text-mutedForeground">
                See what is exposed, why it is becoming risky, how it formed, and how much to trust the signal.
              </p>
            </div>
            <Link
              href="/dashboard/risk-workspace"
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-semibold hover:border-primary"
            >
              Open workspace
              <ArrowRight className="h-4 w-4" />
            </Link>
          </CardContent>
        </Card>

        <section className="grid min-w-0 gap-3 md:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "Critical risks", value: String(kpis?.critical_risks ?? 0), trend: "immediate continuity threat" },
            { label: "Warning risks", value: String(kpis?.warning_risks ?? 0), trend: "requires active monitoring" },
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
                <CardHeader className="min-w-0 space-y-2 px-4 pb-2 pt-4">
                  <div className="absolute right-4 top-4 rounded-xl bg-muted p-2.5 text-primary">
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 pr-12">
                    <CardTitle className="text-sm font-medium leading-snug text-mutedForeground">
                      {metric.label}
                    </CardTitle>
                    <p className="mt-2 break-words text-xl font-semibold leading-tight tracking-tight">{metric.value}</p>
                  </div>
                </CardHeader>
                <CardContent className="px-4 pb-4">
                  <p className="break-words text-sm leading-snug text-mutedForeground">{metric.trend}</p>
                </CardContent>
              </Card>
            );
          })}
        </section>

        <section className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(280px,0.75fr)]">
          <Card className="min-w-0 bg-card/90 shadow-panel">
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle>Current exposure signals</CardTitle>
                <Link
                  href="/dashboard/risk-workspace"
                  className="rounded-xl border px-3 py-2 text-xs font-semibold"
                >
                  Review workspace
                </Link>
              </div>
              <p className="text-sm text-mutedForeground">
                Highest-priority plant/material continuity signals from available stock.
              </p>
              <div className="mt-3 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950">
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
                    <div className="mt-4 grid min-w-0 gap-3 border-t pt-4 md:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
                      <DecisionField label="Signal" value={rootCauseFor(row)} />
                      <div className="min-w-0">
                        <p className="text-xs uppercase tracking-[0.18em] text-mutedForeground">Exposure value</p>
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

          <div className="grid gap-4">
            <AutomatedFreshnessCard summary={executive?.automated_data_freshness ?? null} />
            <FreshnessCard
              title="Data freshness"
              items={[
                ["Stock", executive?.stock_freshness.freshness_label ?? "unknown", executive?.stock_freshness.last_updated_at ?? null],
                ["Exceptions", executive?.exception_freshness.freshness_label ?? "unknown", executive?.exception_freshness.last_updated_at ?? null],
                ["Movement", executive?.movement_freshness.freshness_label ?? "unknown", executive?.movement_freshness.last_updated_at ?? null],
              ]}
            />
          </div>
        </section>
      </div>
    </main>
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
                Microsoft Graph sync refreshes stock exposure and signal freshness live. Delta counters are shown for legacy URL sync sources only.
              </div>
            ) : (
              <div className="rounded-xl bg-muted px-4 py-3 text-mutedForeground">
                <p>+{summary.last_sync_summary.new_critical_risks_count} new critical risks</p>
                <p>-{summary.last_sync_summary.resolved_risks_count} risks resolved</p>
                <p>{summary.last_sync_summary.newly_breached_actions_count} timing breaches detected</p>
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

function formatAssumptionLine(valuePerMt: string | null, multiplier: string | null) {
  if (!valuePerMt || !multiplier) {
    return "Assumptions unavailable";
  }
  return `(Assumes ${displayCurrency(valuePerMt)}/MT x ${trimNumber(multiplier)})`;
}

function trimNumber(value: string) {
  return Number(value).toString();
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
