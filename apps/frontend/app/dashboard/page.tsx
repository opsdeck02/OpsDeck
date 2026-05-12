import Link from "next/link";
import { redirect } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  Clock3,
  ShieldAlert,
  TimerReset,
} from "lucide-react";

import { DailyBriefButton } from "@/components/reports/daily-brief-button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getCurrentUser,
  getExecutiveDashboard,
  getStockCoverSummary,
} from "@/lib/api";
import { selectedPlantContext } from "@/lib/plant-context";

export const dynamic = "force-dynamic";

const icons = [Boxes, ShieldAlert, AlertTriangle, TimerReset];

export default async function DashboardPage({
  searchParams,
}: {
  searchParams?: { plant_reference?: string };
}) {
  const [executive, user, stockSummary] = await Promise.all([
    getExecutiveDashboard(),
    getCurrentUser(),
    getStockCoverSummary(),
  ]);
  if (user?.is_superadmin) {
    redirect("/dashboard/superadmin");
  }
  const plantOptions = uniquePlantOptionsFromStock(stockSummary?.rows ?? []);
  const selectedPlant = selectedPlantContext(
    plantOptions,
    searchParams?.plant_reference,
  );
  const selectedPlantId = selectedPlant?.plantId;
  const plantContextLabel = selectedPlant?.label ?? "All plants";
  const activeTenant = executive?.tenant ?? "demo-steel";
  const filteredStockRows =
    selectedPlantId === undefined
      ? (stockSummary?.rows ?? [])
      : (stockSummary?.rows ?? []).filter(
          (row) => row.plant_id === selectedPlantId,
        );
  const filteredExecutiveRisks =
    selectedPlantId === undefined
      ? (executive?.top_risks ?? [])
      : (executive?.top_risks ?? []).filter(
          (row) => row.plant_id === selectedPlantId,
        );
  const kpis = selectedPlant
    ? {
        critical_risks: filteredStockRows.filter(
          (row) => row.calculation.status === "critical",
        ).length,
        warning_risks: filteredStockRows.filter(
          (row) => row.calculation.status === "warning",
        ).length,
      }
    : executive?.kpis;
  const topRisks = filteredExecutiveRisks;
  const criticalRisks = kpis?.critical_risks ?? 0;
  const shortestDaysToLineStop = shortestDays(topRisks);
  const leadRisk = topRisks[0] ?? null;
  const dataFreshnessLabel =
    executive?.automated_data_freshness?.data_freshness_status ??
    executive?.stock_freshness.freshness_label ??
    "unknown";

  return (
    <main className="min-w-0">
      <div className="flex min-w-0 flex-col gap-3">
        <section className="overflow-hidden rounded-3xl bg-slate-950 text-white shadow-nerve">
          <div className="grid gap-3 p-3 lg:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
            <div className="min-w-0 rounded-2xl bg-white/[0.06] p-3.5 ring-1 ring-white/10">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    className={
                      leadRisk?.status === "critical"
                        ? "bg-red-500 text-white"
                        : criticalRisks > 0
                          ? "bg-red-500 text-white"
                          : "bg-blue-500 text-white"
                    }
                  >
                    Continuity exposure overview
                  </Badge>
                  <span className="text-xs text-white/60">
                    {activeTenant} · {plantContextLabel}
                  </span>
                </div>
                <DailyBriefButton compact />
              </div>
              <h1 className="mt-3 max-w-3xl text-3xl font-semibold leading-tight tracking-tight lg:text-[2.4rem]">
                {leadRisk
                  ? `${leadRisk.material_name} exposure at ${leadRisk.plant_name}`
                  : "No critical exposure detected"}
              </h1>
              <p className="text-white/68 mt-2 max-w-2xl text-sm leading-5">
                {leadRisk
                  ? `${rootCauseFor(leadRisk)}. Available cover is ${displayDays(leadRisk.days_of_cover)} with next inbound ${formatDate(leadRisk.next_inbound_eta)}.`
                  : selectedPlant
                    ? `Operational continuity remains stable for ${plantContextLabel}.`
                    : "Operational continuity remains stable across monitored inbound dependencies."}
              </p>
              <Link
                href={dashboardHref(
                  "/dashboard/risk-workspace",
                  searchParams?.plant_reference,
                )}
                className="mt-4 inline-flex items-center gap-2 rounded-xl bg-white px-3.5 py-2 text-sm font-semibold text-slate-950"
              >
                Open risk workspace
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
            <div className="grid min-w-0 gap-3 sm:grid-cols-2">
              <PressureMetric
                label="How soon"
                value={displayDays(shortestDaysToLineStop)}
                helper="shortest available cover"
                tone={criticalRisks > 0 ? "critical" : "passive"}
                priority
              />
              <PressureMetric
                label="Exposed operation"
                value={leadRisk?.material_name ?? "None"}
                helper={leadRisk?.plant_name ?? "Loaded context"}
                tone={criticalRisks > 0 ? "critical" : "info"}
              />
              <PressureMetric
                label="Why"
                value={leadRisk ? rootCauseFor(leadRisk) : "Stable cover"}
                helper="continuity driver"
                tone={
                  leadRisk?.status === "warning"
                    ? "warning"
                    : criticalRisks > 0
                      ? "critical"
                      : "passive"
                }
              />
              <PressureMetric
                label="Trust"
                value={dataFreshnessLabel}
                helper={
                  executive?.automated_data_freshness
                    ? `${executive.automated_data_freshness.data_freshness_age_minutes ?? "unknown"} min age`
                    : "stock freshness"
                }
                tone={freshnessTone(dataFreshnessLabel)}
              />
            </div>
          </div>
        </section>

        {!executive ? (
          <Card className="bg-card/90 shadow-panel">
            <CardHeader>
              <CardTitle>Continuity overview unavailable</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-mutedForeground">
              The continuity overview could not be loaded. Confirm you are
              signed in to the correct tenant and try again.
            </CardContent>
          </Card>
        ) : null}

        {searchParams?.plant_reference && !selectedPlant ? (
          <Card className="bg-card/90 shadow-panel">
            <CardContent className="py-3 text-sm text-mutedForeground">
              This view is tenant-wide until plant-level source data is
              available for {searchParams.plant_reference}.
            </CardContent>
          </Card>
        ) : null}

        {criticalRisks > 0 ? (
          <section className="rounded-2xl bg-red-50 px-4 py-3 text-red-950 ring-1 ring-red-200">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="rounded-xl bg-red-600 p-2.5 text-white">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-lg font-semibold">
                  Plant continuity risk active
                </h2>
                <p className="mt-1 text-sm text-red-900">
                  {criticalRisks} critical material dependencies are inside the
                  operating buffer
                  {selectedPlant ? ` for ${plantContextLabel}` : ""}.
                </p>
              </div>
            </div>
          </section>
        ) : null}

        <section className="grid min-w-0 gap-2.5 md:grid-cols-2 xl:grid-cols-4">
          {[
            {
              label: "Critical exposure",
              value: String(kpis?.critical_risks ?? 0),
              trend: "immediate continuity threat",
            },
            {
              label: "Degrading cover",
              value: String(kpis?.warning_risks ?? 0),
              trend: "continuity pressure building",
            },
            {
              label: "Shortest days to line stop",
              value: displayDays(shortestDaysToLineStop),
              trend: "based only on available stock",
            },
            {
              label: "Signal trust",
              value: dataFreshnessLabel,
              trend: executive?.automated_data_freshness
                ? `age ${executive.automated_data_freshness.data_freshness_age_minutes ?? "unknown"} min`
                : "stock snapshot status",
            },
          ].map((metric, index) => {
            const Icon = icons[index % icons.length];
            return (
              <Card
                key={metric.label}
                className="relative min-w-0 overflow-hidden"
              >
                <CardHeader className="min-w-0 space-y-2">
                  <div className="absolute right-4 top-4 rounded-xl bg-slate-100 p-2 text-mutedForeground">
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 pr-12">
                    <CardTitle className="text-sm font-medium leading-snug text-mutedForeground">
                      {metric.label}
                    </CardTitle>
                    <p className="mt-2 break-words text-2xl font-semibold leading-tight tracking-tight">
                      {metric.value}
                    </p>
                  </div>
                </CardHeader>
                <CardContent className="px-4 pb-4">
                  <p className="break-words text-sm leading-snug text-mutedForeground">
                    {metric.trend}
                  </p>
                </CardContent>
              </Card>
            );
          })}
        </section>

        <section className="grid min-w-0 gap-3 xl:grid-cols-[minmax(0,1.34fr)_minmax(280px,0.66fr)]">
          <Card className="min-w-0">
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle>Current exposure signals</CardTitle>
                <Link
                  href={dashboardHref(
                    "/dashboard/risk-workspace",
                    searchParams?.plant_reference,
                  )}
                  className="rounded-xl border px-3 py-2 text-xs font-semibold"
                >
                  Review workspace
                </Link>
              </div>
              <p className="text-sm text-mutedForeground">
                {selectedPlant
                  ? `Viewing continuity for ${plantContextLabel}.`
                  : "Highest-pressure operating contexts across All plants."}
              </p>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {topRisks.map((row) => (
                  <div
                    key={`${row.plant_id}-${row.material_id}`}
                    className={`min-w-0 rounded-2xl p-3 ring-1 ${signalRowClass(row.status)}`}
                  >
                    <div className="flex min-w-0 flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                      <div className="min-w-0">
                        <Link
                          href={`/dashboard/stock-cover/${row.plant_id}/${row.material_id}`}
                          className="break-words text-base font-semibold text-foreground hover:text-primary"
                        >
                          {row.material_name}
                        </Link>
                        <p className="mt-1 break-words text-sm text-mutedForeground">
                          {row.plant_name}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge status={row.status} />
                        <span className="rounded-full bg-white/70 px-2.5 py-1 text-xs font-semibold text-slate-700 ring-1 ring-slate-900/10">
                          {rootCauseFor(row)}
                        </span>
                      </div>
                    </div>
                    <div className="mt-3 grid min-w-0 gap-2 sm:grid-cols-2 xl:grid-cols-[1.15fr_0.9fr_0.9fr_1.2fr]">
                      <RiskMetric
                        label="Projected failure"
                        value={displayDays(row.days_of_cover)}
                        helper={`threshold ${displayDays(row.threshold_days)}`}
                        prominent
                        tone="critical"
                      />
                      <RiskMetric
                        label="Usable now"
                        value={displayTonnes(row.usable_stock_mt)}
                        helper="available cover"
                      />
                      <RiskMetric
                        label="Blocked"
                        value={displayTonnes(row.blocked_stock_mt)}
                        tone="warning"
                      />
                      <RiskMetric
                        label="Incoming"
                        value={displayTonnes(row.raw_inbound_pipeline_mt)}
                        helper={`next ${formatDate(row.next_inbound_eta)}`}
                      />
                    </div>
                    <div className="mt-3 grid min-w-0 gap-3 border-t border-slate-900/10 pt-3 md:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
                      <DecisionField label="Signal" value={rootCauseFor(row)} />
                      <div className="min-w-0">
                        <p className="text-xs font-semibold text-mutedForeground">
                          Exposure value
                        </p>
                        <p className="mt-1 font-semibold text-foreground">
                          {displayCurrency(row.estimated_value_at_risk)}
                        </p>
                        <p className="mt-1 break-words text-xs text-mutedForeground">
                          {displayTonnes(row.estimated_production_exposure_mt)}{" "}
                          exposed ·{" "}
                          {formatAssumptionLine(
                            row.value_per_mt_used,
                            row.criticality_multiplier_used,
                          )}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
                {topRisks.length === 0 ? (
                  <div className="rounded-2xl bg-slate-50 px-4 py-8 text-center text-sm text-mutedForeground ring-1 ring-slate-900/5">
                    {filteredStockRows.length > 0
                      ? `${filteredStockRows.length} operating contexts loaded. No continuity exposure is currently flagged.`
                      : "Operational continuity remains calm across loaded contexts."}
                  </div>
                ) : null}
              </div>
              {topRisks.length === 0 && filteredStockRows.length > 0 ? (
                <div className="mt-3 rounded-2xl bg-slate-50 p-3 text-sm ring-1 ring-slate-900/5">
                  <p className="font-semibold">Continuity signals loaded</p>
                  <p className="mt-1 text-mutedForeground">
                    Operating buffers are holding{" "}
                    {selectedPlant
                      ? `for ${plantContextLabel}`
                      : "across monitored plant/material dependencies"}
                    .
                  </p>
                  <div className="mt-3 grid gap-2 md:grid-cols-2">
                    {filteredStockRows.slice(0, 4).map((row) => (
                      <Link
                        key={`${row.plant_id}-${row.material_id}`}
                        href={`/dashboard/stock-cover/${row.plant_id}/${row.material_id}`}
                        className="rounded-xl bg-white px-3 py-2.5 ring-1 ring-slate-900/5 hover:ring-primary/40"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-medium">
                            {row.material_name}
                          </span>
                          <StatusBadge status={row.calculation.status} />
                        </div>
                        <p className="mt-1 text-mutedForeground">
                          {row.plant_name} ·{" "}
                          {displayDays(row.calculation.days_of_cover)} cover
                        </p>
                      </Link>
                    ))}
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <div className="grid gap-4">
            <AutomatedFreshnessCard
              summary={executive?.automated_data_freshness ?? null}
              freshness={dataFreshnessLabel}
            />
            <FreshnessCard
              title="Signal trust status"
              items={[
                [
                  "Inventory signal",
                  executive?.stock_freshness.freshness_label ?? "unknown",
                  executive?.stock_freshness.last_updated_at ?? null,
                ],
                [
                  "Continuity signal",
                  executive?.exception_freshness.freshness_label ?? "unknown",
                  executive?.exception_freshness.last_updated_at ?? null,
                ],
                [
                  "Inbound signal",
                  executive?.movement_freshness.freshness_label ?? "unknown",
                  executive?.movement_freshness.last_updated_at ?? null,
                ],
              ]}
            />
          </div>
        </section>
      </div>
    </main>
  );
}

function uniquePlantOptionsFromStock(
  rows: Array<{ plant_id: number; plant_code: string; plant_name: string }>,
) {
  const options = new Map<
    string,
    { reference: string; label: string; plantId: number }
  >();
  for (const row of rows) {
    if (!row.plant_code) continue;
    options.set(row.plant_code, {
      reference: row.plant_code,
      label: row.plant_name || row.plant_code,
      plantId: row.plant_id,
    });
  }
  return [...options.values()];
}

function dashboardHref(href: string, plantReference?: string) {
  if (!plantReference) return href;
  return `${href}?${new URLSearchParams({ plant_reference: plantReference }).toString()}`;
}

function RiskMetric({
  label,
  value,
  helper,
  prominent = false,
  tone = "default",
}: {
  label: string;
  value: string;
  helper?: string;
  prominent?: boolean;
  tone?: "default" | "critical" | "warning";
}) {
  const toneClass =
    tone === "critical"
      ? "bg-red-50 text-red-950 ring-red-200"
      : tone === "warning"
        ? "bg-amber-50 text-amber-950 ring-amber-200"
        : "bg-white/62 text-foreground ring-slate-900/5";
  return (
    <div className={`min-w-0 rounded-xl px-3 py-2 ring-1 ${toneClass}`}>
      <p className="text-xs font-semibold text-mutedForeground">{label}</p>
      <p
        className={`mt-1 break-words font-semibold ${prominent ? "text-xl" : ""}`}
      >
        {value}
      </p>
      {helper ? (
        <p className="mt-1 break-words text-xs text-mutedForeground">
          {helper}
        </p>
      ) : null}
    </div>
  );
}

function PressureMetric({
  label,
  value,
  helper,
  tone,
  priority = false,
}: {
  label: string;
  value: string;
  helper: string;
  tone: "critical" | "warning" | "info" | "passive";
  priority?: boolean;
}) {
  const toneClass =
    tone === "critical"
      ? "bg-red-500/14 text-red-50 ring-red-300/30"
      : tone === "warning"
        ? "bg-amber-400/14 text-amber-50 ring-amber-200/30"
        : tone === "info"
          ? "bg-blue-400/14 text-blue-50 ring-blue-200/30"
          : "bg-white/8 text-white ring-white/10";
  return (
    <div className={`min-w-0 rounded-2xl p-3.5 ring-1 ${toneClass}`}>
      <p className="text-xs font-semibold text-white/55">{label}</p>
      <p
        className={`mt-2 truncate font-semibold leading-none ${priority ? "text-4xl text-white" : "text-2xl"}`}
      >
        {value}
      </p>
      <p className="text-white/58 mt-1.5 truncate text-xs">{helper}</p>
    </div>
  );
}

function DecisionField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-semibold text-mutedForeground">{label}</p>
      <p className="mt-1 break-words font-medium text-foreground">{value}</p>
    </div>
  );
}

function AutomatedFreshnessCard({
  summary,
  freshness,
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
  freshness: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Signal trust status</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {!summary ? (
          <TrustLine
            label="Freshness"
            value={freshness}
            tone={freshnessTone(freshness)}
          />
        ) : (
          <>
            <TrustLine
              label="Freshness"
              value={summary.data_freshness_status}
              tone={freshnessTone(summary.data_freshness_status)}
            />
            <TrustLine
              label="Sync age"
              value={
                summary.data_freshness_age_minutes !== null
                  ? `${summary.data_freshness_age_minutes} min`
                  : "not synced"
              }
              tone={
                summary.data_freshness_age_minutes !== null &&
                summary.data_freshness_age_minutes > 240
                  ? "warning"
                  : "info"
              }
            />
            <TrustLine
              label="Sync failures"
              value={
                summary.last_sync_summary.last_sync_status ?? "not started"
              }
              tone={
                summary.last_sync_summary.last_sync_status === "failed"
                  ? "critical"
                  : "passive"
              }
            />
            <TrustLine
              label="New exposure"
              value={String(summary.last_sync_summary.new_critical_risks_count)}
              tone={
                summary.last_sync_summary.new_critical_risks_count > 0
                  ? "critical"
                  : "passive"
              }
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function FreshnessCard({
  title,
  items,
}: {
  title: string;
  items: Array<[string, string, string | null]>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {items.map(([label, freshness, updatedAt]) => (
          <div
            key={label}
            className={`rounded-xl px-3 py-2 ring-1 ${trustToneClass(freshnessTone(freshness))}`}
          >
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

function TrustLine({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "critical" | "warning" | "info" | "passive";
}) {
  return (
    <div
      className={`flex items-center justify-between gap-3 rounded-xl px-3 py-2 ring-1 ${trustToneClass(tone)}`}
    >
      <span className="text-sm font-medium">{label}</span>
      <span className="text-sm font-semibold">{value}</span>
    </div>
  );
}

function trustToneClass(tone: "critical" | "warning" | "info" | "passive") {
  if (tone === "critical") return "bg-red-50 text-red-900 ring-red-200";
  if (tone === "warning") return "bg-amber-50 text-amber-900 ring-amber-200";
  if (tone === "info") return "bg-blue-50 text-blue-900 ring-blue-200";
  return "bg-slate-50 text-slate-700 ring-slate-200";
}

function StatusBadge({ status }: { status: string }) {
  const className =
    status === "critical"
      ? "od-status-critical"
      : status === "warning"
        ? "od-status-warning"
        : status === "insufficient_data"
          ? "od-status-passive"
          : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200";
  const label = status === "safe" ? "healthy" : status.replace("_", " ");
  return (
    <span
      className={`rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}
    >
      {label}
    </span>
  );
}

function signalRowClass(status: string) {
  if (status === "critical") return "bg-red-50/90 ring-red-200";
  if (status === "warning") return "bg-amber-50/90 ring-amber-200";
  return "bg-slate-50 ring-slate-200/70";
}

function freshnessTone(
  value: string,
): "critical" | "warning" | "info" | "passive" {
  const normalized = value.toLowerCase();
  if (normalized.includes("critical") || normalized.includes("stale"))
    return "critical";
  if (normalized.includes("aging") || normalized.includes("delayed"))
    return "warning";
  if (normalized.includes("fresh")) return "info";
  return "passive";
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
  const lineStopDate =
    days !== null ? new Date(Date.now() + days * 24 * 60 * 60 * 1000) : null;

  if (available <= 0) {
    return "Usable cover exhausted";
  }
  if (blocked > available) {
    return "Quality hold reducing cover";
  }
  if (nextEta && lineStopDate && nextEta > lineStopDate) {
    return "Inbound arrives after buffer";
  }
  if (threshold !== null && days !== null && days <= threshold) {
    return "Operating buffer breached";
  }
  return "Buffer watch";
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

function formatAssumptionLine(
  valuePerMt: string | null,
  multiplier: string | null,
) {
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
