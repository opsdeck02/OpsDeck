import { redirect } from "next/navigation";
import { Download, ScrollText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getCurrentUser,
  getExecutiveContinuityReport,
  type ExecutiveMaterialRisk,
} from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ExecutiveContinuityReportPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const isTenantAdmin = user.memberships[0]?.role === "tenant_admin";
  if (!isTenantAdmin && !user.is_superadmin) redirect("/dashboard");

  const report = await getExecutiveContinuityReport();
  if (!report) {
    return (
      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Executive continuity report unavailable</CardTitle>
          <p className="text-sm text-mutedForeground">
            OpsDeck could not load the executive continuity report for this tenant.
          </p>
        </CardHeader>
      </Card>
    );
  }

  const exportHref = `data:text/markdown;charset=utf-8,${encodeURIComponent(
    report.markdown_report,
  )}`;

  return (
    <div className="grid gap-4">
      <section className="rounded-2xl bg-card/90 p-6 shadow-panel ring-1 ring-slate-900/5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-mutedForeground">
              <ScrollText className="h-4 w-4" />
              Executive Continuity Report
            </div>
            <h1 className="mt-3 text-3xl font-semibold text-foreground">
              Continuity briefing for {report.summary.tenant}
            </h1>
            <p className="mt-2 text-sm leading-6 text-mutedForeground">
              Generated {formatDateTime(report.summary.generated_at)} ·{" "}
              {report.summary.plant_scope}
            </p>
          </div>
          <a
            href={exportHref}
            download="executive-continuity-report.md"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 shadow-sm transition hover:border-primary/40 hover:text-primary"
          >
            <Download className="h-4 w-4" />
            Export report
          </a>
        </div>

        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Materials assessed" value={report.summary.materials_assessed} />
          <Metric label="Critical materials" value={report.summary.critical_materials} />
          <Metric label="High risk materials" value={report.summary.high_risk_materials} />
          <Metric
            label="Historical detection"
            value={displayPercent(report.summary.historical_validation_detection_rate)}
          />
          <Metric
            label="Assessment calibration"
            value={report.summary.average_assessment_calibration}
          />
          <Metric
            label="Calibration score"
            value={displayPercent(report.summary.average_assessment_calibration_score)}
          />
          <Metric label="Operational trust" value={report.summary.average_operational_trust} />
          <Metric
            label="Trust score"
            value={displayPercent(report.summary.average_operational_trust_score)}
          />
        </div>
      </section>

      <section className="grid gap-3">
        <SectionTitle
          title="Critical Materials"
          subtitle="Critical and high material risks that need executive attention."
        />
        {report.critical_materials.length > 0 ? (
          report.critical_materials.map((material) => (
            <MaterialBrief
              key={`${material.plant_reference}-${material.material_reference}`}
              material={material}
            />
          ))
        ) : (
          <Card className="bg-card/90 shadow-panel">
            <CardHeader>
              <CardTitle>No critical or high materials in scope</CardTitle>
              <p className="text-sm text-mutedForeground">
                OpsDeck did not find critical or high continuity material risks.
              </p>
            </CardHeader>
          </Card>
        )}
      </section>

      <section className="grid gap-3 lg:grid-cols-2">
        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Historical Validation</CardTitle>
            <p className="text-sm leading-6 text-mutedForeground">
              {report.historical_validation.interpretation}
            </p>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <Metric
              label="Detection rate"
              value={displayPercent(report.historical_validation.detection_rate)}
            />
            <Metric
              label="Avg lead time"
              value={displayDays(report.historical_validation.average_warning_lead_time_days)}
            />
            <Metric
              label="Detected incidents"
              value={report.historical_validation.detected_incidents}
            />
            <Metric
              label="Missed incidents"
              value={report.historical_validation.missed_incidents}
            />
          </CardContent>
        </Card>

        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Recommended Actions</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <ActionList
              title="Immediate"
              items={report.recommended_actions.immediate ?? []}
            />
            <ActionList
              title="Short-Term"
              items={report.recommended_actions.short_term ?? []}
            />
            <ActionList
              title="Data / Calibration"
              items={report.recommended_actions.calibration ?? []}
            />
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function MaterialBrief({ material }: { material: ExecutiveMaterialRisk }) {
  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader className="gap-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-mutedForeground">
              {material.plant_reference ?? material.plant}
            </p>
            <CardTitle className="mt-2">{material.material}</CardTitle>
            <p className="mt-1 text-sm text-mutedForeground">
              {material.material_reference ?? "Material reference unavailable"}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge className={severityTone(material.severity)}>
              {formatLabel(material.severity)}
            </Badge>
            <Badge variant="outline">{material.recommended_priority}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-5">
        <div className="grid gap-3 md:grid-cols-4">
          <Metric label="Current cover" value={displayDays(material.current_usable_cover)} />
          <Metric label="Earliest breach" value={formatDate(material.earliest_breach_date)} />
          <Metric label="Operational trust" value={formatLabel(material.operational_trust)} />
          <Metric
            label="Calibration"
            value={formatLabel(material.assessment_calibration?.status ?? "unknown")}
          />
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <ReportList title="Why This Is Escalating" items={material.why_escalating} />
          <div className="rounded-xl bg-slate-50 p-4 ring-1 ring-slate-900/5">
            <h3 className="text-sm font-semibold text-foreground">
              Inbound Protection Quality
            </h3>
            <p className="mt-2 text-sm leading-6 text-mutedForeground">
              {material.inbound_protection?.interpretation ?? "Unavailable"}
            </p>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              <MiniFact
                label="Physical"
                value={displayQuantity(material.inbound_protection?.physical_inbound)}
              />
              <MiniFact
                label="Trusted"
                value={displayQuantity(material.inbound_protection?.trusted_inbound)}
              />
              <MiniFact
                label="Uncertain"
                value={displayQuantity(material.inbound_protection?.visibility_uncertainty)}
              />
            </div>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl bg-slate-50 p-4 ring-1 ring-slate-900/5">
            <h3 className="text-sm font-semibold text-foreground">
              Time-Phased Continuity Projection
            </h3>
            <p className="mt-2 text-sm leading-6 text-mutedForeground">
              {material.continuity_projection?.interpretation ?? "Unavailable"}
            </p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <MiniFact
                label="Warning"
                value={formatDate(material.continuity_projection?.warning_date)}
              />
              <MiniFact
                label="Reserve"
                value={formatDate(material.continuity_projection?.reserve_breach_date)}
              />
              <MiniFact
                label="Critical"
                value={formatDate(material.continuity_projection?.critical_breach_date)}
              />
              <MiniFact
                label="Interruption"
                value={formatDate(material.continuity_projection?.interruption_date)}
              />
            </div>
          </div>
          <div className="rounded-xl bg-slate-50 p-4 ring-1 ring-slate-900/5">
            <h3 className="text-sm font-semibold text-foreground">
              Assessment Calibration
            </h3>
            <p className="mt-2 text-sm leading-6 text-mutedForeground">
              {material.assessment_calibration?.summary ?? "Calibration unavailable."}
            </p>
            <ReportList
              title="What would improve trust"
              items={material.calibration_actions}
              compact
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-mutedForeground">
        {label}
      </p>
      <p className="mt-2 text-xl font-semibold text-foreground">{value}</p>
    </div>
  );
}

function MiniFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white px-3 py-2 ring-1 ring-slate-900/5">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-mutedForeground">
        {label}
      </p>
      <p className="mt-1 text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}

function SectionTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div>
      <h2 className="text-xl font-semibold text-foreground">{title}</h2>
      <p className="mt-1 text-sm text-mutedForeground">{subtitle}</p>
    </div>
  );
}

function ActionList({ title, items }: { title: string; items: string[] }) {
  return <ReportList title={title} items={items} compact />;
}

function ReportList({
  title,
  items,
  compact = false,
}: {
  title: string;
  items: string[];
  compact?: boolean;
}) {
  const visible = items.filter(Boolean).slice(0, compact ? 4 : 6);
  return (
    <div>
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      {visible.length > 0 ? (
        <ul className="mt-2 grid gap-2 text-sm leading-6 text-mutedForeground">
          {visible.map((item) => (
            <li key={item} className="rounded-lg bg-white px-3 py-2 ring-1 ring-slate-900/5">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 rounded-lg bg-white px-3 py-2 text-sm text-mutedForeground ring-1 ring-slate-900/5">
          No items returned.
        </p>
      )}
    </div>
  );
}

function severityTone(severity: string) {
  if (severity === "critical") return "bg-red-50 text-red-700 ring-1 ring-red-200";
  if (severity === "high") return "bg-amber-50 text-amber-700 ring-1 ring-amber-200";
  return "bg-slate-50 text-slate-700 ring-1 ring-slate-200";
}

function formatLabel(value: string | null | undefined) {
  if (!value) return "Unknown";
  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/^\w/, (char) => char.toUpperCase());
}

function formatDate(value: string | null | undefined) {
  if (!value) return "N/A";
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function displayDays(value: string | null | undefined) {
  return value ? `${value} d` : "N/A";
}

function displayPercent(value: string | null | undefined) {
  return value ? `${value}%` : "N/A";
}

function displayQuantity(value: string | null | undefined) {
  return value ? `${value} MT` : "N/A";
}
