"use client";

import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ValidationFinding {
  finding_code: string;
  severity: "error" | "warning" | "info";
  area: string;
  title: string;
  description: string;
  operational_impact: string;
  suggested_fix: string;
  affects_risk_precision: boolean;
}

interface ValidationResult {
  validation_status: string;
  readiness_score: string;
  findings: ValidationFinding[];
  blocking_errors_count: number;
  warnings_count: number;
  info_count: number;
}

export function ConfigurationValidationSummary({
  plantId,
  materialId,
}: {
  plantId: number;
  materialId: number;
}) {
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!plantId || !materialId) {
      setResult(null);
      return;
    }
    const query = new URLSearchParams({
      plant_id: String(plantId),
      material_id: String(materialId),
    });
    setError("");
    fetch(`/api/impact/configuration-validation?${query.toString()}`, {
      cache: "no-store",
    })
      .then(async (response) => {
        if (!response.ok) {
          const body = (await response.json().catch(() => null)) as
            | { detail?: string }
            | null;
          throw new Error(body?.detail ?? "Could not load validation summary.");
        }
        setResult((await response.json()) as ValidationResult);
      })
      .catch((err) => {
        setResult(null);
        setError(
          err instanceof Error
            ? err.message
            : "Could not load validation summary.",
        );
      });
  }, [materialId, plantId]);

  return (
    <Card className="bg-slate-50/80 shadow-none ring-1 ring-slate-900/5">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">Configuration readiness</CardTitle>
          {result ? (
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${statusClass(
                result.validation_status,
              )}`}
            >
              {formatLabel(result.validation_status)}
            </span>
          ) : null}
        </div>
        <p className="text-xs leading-5 text-mutedForeground">
          Deterministic sanity checks for missing, contradictory, or unrealistic
          operational assumptions.
        </p>
      </CardHeader>
      <CardContent>
        {result ? (
          <div className="grid gap-2.5">
            <div className="grid gap-2 sm:grid-cols-2">
              <SummaryPill
                label="Readiness score"
                value={`${formatNumber(result.readiness_score)}%`}
              />
              <SummaryPill
                label="Findings"
                value={`${result.blocking_errors_count} errors · ${result.warnings_count} warnings · ${result.info_count} info`}
              />
            </div>
            {result.findings.length > 0 ? (
              <div className="space-y-2">
                {result.findings.slice(0, 3).map((finding) => (
                  <div
                    key={finding.finding_code}
                    className="rounded-xl bg-white px-3 py-2 ring-1 ring-slate-900/5"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[0.68rem] font-semibold uppercase tracking-[0.12em] ${severityClass(
                          finding.severity,
                        )}`}
                      >
                        {finding.severity}
                      </span>
                      <p className="text-sm font-semibold">{finding.title}</p>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-mutedForeground">
                      {finding.operational_impact}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rounded-xl bg-white px-3 py-2 text-sm text-mutedForeground ring-1 ring-slate-900/5">
                No configuration sanity findings for this context.
              </p>
            )}
          </div>
        ) : (
          <p className="rounded-xl bg-white px-3 py-2 text-sm text-mutedForeground ring-1 ring-slate-900/5">
            {error || "Validation summary is not available for this context yet."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function SummaryPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white px-3 py-2 ring-1 ring-slate-900/5">
      <p className="text-xs font-semibold text-mutedForeground">{label}</p>
      <p className="mt-1 text-sm font-semibold">{value}</p>
    </div>
  );
}

function statusClass(status: string) {
  if (status === "ready") return "bg-emerald-50 text-emerald-800 ring-emerald-200";
  if (status === "usable_with_warnings")
    return "bg-blue-50 text-blue-800 ring-blue-200";
  if (status === "invalid") return "bg-red-50 text-red-800 ring-red-200";
  return "bg-amber-50 text-amber-900 ring-amber-200";
}

function severityClass(severity: string) {
  if (severity === "error") return "bg-red-50 text-red-800";
  if (severity === "warning") return "bg-amber-50 text-amber-900";
  return "bg-slate-100 text-slate-700";
}

function formatLabel(value: string) {
  return value.replaceAll("_", " ");
}

function formatNumber(value: string) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return value;
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
