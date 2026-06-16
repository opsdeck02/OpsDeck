import { redirect } from "next/navigation";
import { Download, FileClock } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getCurrentUser,
  getHistoricalValidationReport,
  type HistoricalValidationIncidentResult,
} from "@/lib/api";

export const dynamic = "force-dynamic";

const detectionTone: Record<string, string> = {
  DETECTED: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  "PARTIALLY DETECTED": "bg-amber-50 text-amber-700 ring-amber-200",
  MISSED: "bg-red-50 text-red-700 ring-red-200",
};

const confidenceTone: Record<string, string> = {
  "HIGH CONFIDENCE": "bg-emerald-50 text-emerald-700 ring-emerald-200",
  "MEDIUM CONFIDENCE": "bg-amber-50 text-amber-700 ring-amber-200",
  "LOW CONFIDENCE": "bg-red-50 text-red-700 ring-red-200",
};

export default async function HistoricalValidationPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const isTenantAdmin = user.memberships[0]?.role === "tenant_admin";
  if (!isTenantAdmin && !user.is_superadmin) redirect("/dashboard");

  const report = await getHistoricalValidationReport({ limit: 50 });
  if (!report) {
    return (
      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Past Incident Analysis unavailable</CardTitle>
          <p className="text-sm text-mutedForeground">
            OpsDeck could not load the incident replay report for this tenant.
          </p>
        </CardHeader>
      </Card>
    );
  }

  const summary = report.summary;
  const exportHref = report.report_markdown
    ? `data:text/markdown;charset=utf-8,${encodeURIComponent(report.report_markdown)}`
    : null;

  return (
    <div className="grid gap-4">
      <section className="rounded-2xl bg-card/90 p-6 shadow-panel ring-1 ring-slate-900/5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-mutedForeground">
              <FileClock className="h-4 w-4" />
              Past Incident Analysis
            </div>
            <h1 className="mt-3 text-3xl font-semibold text-foreground">
              Would OpsDeck have seen it before disruption?
            </h1>
            <p className="mt-2 text-sm leading-6 text-mutedForeground">
              Incident Replay for {report.tenant ?? "the active tenant"}.
              Generated {formatDateTime(report.generated_at)}.
            </p>
            <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-sm leading-6 text-mutedForeground ring-1 ring-slate-900/5">
              This replay uses the historical stock, threshold, and inbound
              records available to OpsDeck. It is not statistical ML validation.
            </p>
          </div>
          {exportHref ? (
            <a
              href={exportHref}
              download="incident-replay-report.md"
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 shadow-sm transition hover:border-primary/40 hover:text-primary"
            >
              <Download className="h-4 w-4" />
              Export report
            </a>
          ) : null}
        </div>

        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Incidents analyzed" value={summary?.incidents_analyzed ?? 0} />
          <Metric label="Detected" value={summary?.detected ?? 0} />
          <Metric
            label="Partially detected"
            value={summary?.partially_detected ?? 0}
          />
          <Metric label="Missed" value={summary?.missed ?? 0} />
          <Metric
            label="Detection rate"
            value={`${summary?.detection_rate_percent ?? "0.00"}%`}
          />
          <Metric
            label="Avg warning lead time"
            value={formatDays(summary?.average_warning_lead_time_days)}
          />
          <Metric
            label="Longest warning"
            value={formatDays(summary?.longest_warning_lead_time_days)}
          />
          <Metric
            label="Shortest warning"
            value={formatDays(summary?.shortest_warning_lead_time_days)}
          />
        </div>
      </section>

      <section className="grid gap-3">
        {report.results.length > 0 ? (
          report.results.map((incident) => (
            <IncidentTimelineItem key={incident.incident_id} incident={incident} />
          ))
        ) : (
          <Card className="bg-card/90 shadow-panel">
            <CardHeader>
              <CardTitle>No historical incidents recorded</CardTitle>
              <p className="text-sm text-mutedForeground">
                Add line-stop incidents to validate OpsDeck against past disruptions.
              </p>
            </CardHeader>
          </Card>
        )}
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-mutedForeground">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold text-foreground">{value}</p>
    </div>
  );
}

function IncidentTimelineItem({
  incident,
}: {
  incident: HistoricalValidationIncidentResult;
}) {
  const detectionResult = incident.opsdeck_detection_result ?? "UNKNOWN";
  const confidence = incident.confidence_classification ?? "LOW CONFIDENCE";

  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader className="gap-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-mutedForeground">
              {formatDate(incident.incident_date)} · {formatLabel(incident.incident_type)}
            </p>
            <CardTitle className="mt-2">
              {incident.material_name} at {incident.plant_name}
            </CardTitle>
            <p className="mt-1 text-sm text-mutedForeground">
              {incident.material_reference ?? "Material reference unavailable"} ·{" "}
              {incident.plant_reference ?? "Plant reference unavailable"}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge label={detectionResult} tone={detectionTone[detectionResult]} />
            <StatusBadge label={confidence} tone={confidenceTone[confidence]} />
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-5">
        <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm leading-6 text-mutedForeground ring-1 ring-slate-900/5">
          {incident.status_explanation ?? statusExplanation(detectionResult)}
        </p>
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          <SmallFact
            label="Incident date"
            value={formatDate(incident.incident_date)}
          />
          <SmallFact
            label="Stock position"
            value={
              incident.available_stock_at_snapshot
                ? `${incident.available_stock_at_snapshot} MT on ${formatDate(incident.stock_snapshot_time_used)}`
                : "Unavailable"
            }
          />
          <SmallFact
            label="Inbound position"
            value={`${incident.inbound_quantity_due_before_incident} MT before incident`}
          />
          <SmallFact
            label="Threshold"
            value={
              incident.threshold_days_used || incident.warning_days_used
                ? `Critical ${formatDays(incident.threshold_days_used)}, warning ${formatDays(incident.warning_days_used)}`
                : "Unavailable"
            }
          />
          <SmallFact
            label="OpsDeck warning date"
            value={formatDate(incident.predicted_warning_date)}
          />
          <SmallFact
            label="Lead time available"
            value={formatDays(incident.warning_lead_time_days)}
          />
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <SmallFact
            label="Daily consumption used"
            value={
              incident.daily_consumption_used
                ? `${incident.daily_consumption_used} MT/day`
                : "Unavailable"
            }
          />
          <SmallFact
            label="First inbound ETA"
            value={formatDate(incident.first_inbound_eta)}
          />
          <SmallFact
            label="Line stop duration"
            value={
              incident.line_stop_duration_hours
                ? `${incident.line_stop_duration_hours} h`
                : "Unavailable"
            }
          />
        </div>

        <ReviewSection
          title="Limitations"
          items={incident.missing_data_limitations}
        />
        <ReviewSection title="Detection evidence" items={incident.detection_signals} />
        <ReviewSection title="Detection chain" items={incident.detection_chain} />
        <ReviewSection
          title="Recommended actions replay"
          items={incident.recommended_actions_replay}
        />
        <ReviewSection
          title="Confidence assessment"
          items={incident.confidence_rationale}
        />
        {incident.missed_incident_analysis.length > 0 ? (
          <ReviewSection
            title="Missed incident analysis"
            items={incident.missed_incident_analysis}
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

function SmallFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-mutedForeground">
        {label}
      </p>
      <p className="mt-1 text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}

function ReviewSection({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      {items.length > 0 ? (
        <ul className="mt-2 grid gap-2 text-sm leading-6 text-mutedForeground">
          {items.map((item) => (
            <li key={item} className="rounded-lg bg-slate-50 px-3 py-2">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-mutedForeground">
          No modeled evidence available.
        </p>
      )}
    </div>
  );
}

function StatusBadge({ label, tone }: { label: string; tone?: string }) {
  return (
    <Badge className={`ring-1 ${tone ?? "bg-slate-50 text-slate-700 ring-slate-200"}`}>
      {label}
    </Badge>
  );
}

function statusExplanation(status: string) {
  if (status === "DETECTED") {
    return "OpsDeck would have raised a warning before the incident.";
  }
  if (status === "PARTIALLY DETECTED") {
    return "OpsDeck found some warning signs, but the available data was incomplete or late.";
  }
  if (status === "MISSED") {
    return "OpsDeck would not have warned early enough from the available records.";
  }
  return "Replay status is unavailable from the available records.";
}

function formatLabel(value: string | null) {
  if (!value) return "Unavailable";
  return value.replaceAll("_", " ").toLowerCase().replace(/^\w/, (char) => char.toUpperCase());
}

function formatDate(value: string | null) {
  if (!value) return "Unavailable";
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

function formatDateTime(value: string | null) {
  if (!value) return "time unavailable";
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDays(value: string | null | undefined) {
  return value ? `${value} d` : "N/A";
}
