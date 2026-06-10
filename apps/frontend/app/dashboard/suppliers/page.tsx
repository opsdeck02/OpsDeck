import Link from "next/link";
import { redirect } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SupplierCreateForm } from "@/components/suppliers/supplier-controls";
import { getCurrentUser, getSuppliers } from "@/lib/api";
import { canAccessPilotAdmin } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function SuppliersPage({
  searchParams,
}: {
  searchParams?: { plant_reference?: string };
}) {
  const [user, suppliers] = await Promise.all([
    getCurrentUser(),
    getSuppliers({ plant_reference: searchParams?.plant_reference }),
  ]);
  if (user?.is_superadmin) {
    redirect("/dashboard/superadmin");
  }
  const role = user?.memberships[0]?.role;
  const canManage = canAccessPilotAdmin(role);

  return (
    <main className="space-y-4">
      <section className="od-panel px-4 py-5">
        <div className="flex flex-col gap-2">
          <Badge variant="outline">Continuity reliability</Badge>
          <h1 className="text-2xl font-semibold tracking-tight">
            Reliability source patterns
          </h1>
          <p className="text-sm text-mutedForeground">
            {searchParams?.plant_reference
              ? `Viewing continuity for ${searchParams.plant_reference}.`
              : "Viewing continuity for All plants."}
          </p>
        </div>
      </section>

      <SupplierCreateForm canManage={canManage} />

      <Card>
        <CardHeader>
          <CardTitle>Continuity reliability sources</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="od-table-wrap">
            <table className="od-table min-w-[1040px]">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Primary node</th>
                  <th>Materials</th>
                  <th>Reliability</th>
                  <th>On-Time</th>
                  <th>Avg delay</th>
                  <th>Visibility coverage</th>
                  <th>Active exposure</th>
                  <th>Record</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((supplier) => (
                  <tr key={supplier.id}>
                    <td className="font-medium">
                      <Link
                        href={supplierHref(
                          supplier.id,
                          searchParams?.plant_reference,
                        )}
                        className="text-primary hover:underline"
                      >
                        {supplier.name}
                      </Link>
                    </td>
                    <td>{supplier.primary_port ?? "-"}</td>
                    <td>
                      {supplier.performance.materials_supplied.join(", ") ||
                        "-"}
                    </td>
                    <td>
                      <ReliabilityBadge
                        grade={supplier.performance.reliability_grade}
                        status={supplier.performance.reliability_status}
                      />
                    </td>
                    <td>
                      {displayPercent(
                        supplier.performance.on_time_reliability_pct,
                      )}
                    </td>
                    <td>
                      {displayHours(supplier.performance.avg_eta_drift_hours)}
                    </td>
                    <td>
                      {trackingCoverage(supplier.performance.risk_signal_pct)}
                    </td>
                    <td>{supplier.performance.active_shipments}</td>
                    <td>
                      <Link
                        href={supplierHref(
                          supplier.id,
                          searchParams?.plant_reference,
                        )}
                        className="rounded-xl border px-3 py-2 text-xs font-semibold"
                      >
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
                {suppliers.length === 0 ? (
                  <tr>
                    <td
                      className="px-4 py-8 text-center text-mutedForeground"
                      colSpan={9}
                    >
                      {searchParams?.plant_reference
                        ? `No continuity reliability sources are linked to ${searchParams.plant_reference} yet.`
                        : "No continuity reliability sources are active yet."}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}

function supplierHref(supplierId: string, plantReference?: string) {
  if (!plantReference) return `/dashboard/suppliers/${supplierId}`;
  return `/dashboard/suppliers/${supplierId}?${new URLSearchParams({
    plant_reference: plantReference,
  }).toString()}`;
}

function ReliabilityBadge({
  grade,
  status,
}: {
  grade: string;
  status?: string;
}) {
  if (status === "uncalibrated") {
    return (
      <span className="rounded-full bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700 ring-1 ring-slate-200">
        Uncalibrated
      </span>
    );
  }
  const className =
    grade === "A"
      ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
      : grade === "B"
        ? "od-status-info"
        : grade === "C"
          ? "od-status-warning"
          : "od-status-critical";
  return (
    <span
      className={`rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}
    >
      {grade}
    </span>
  );
}

function displayPercent(value: string) {
  return `${Number(value).toFixed(1)}%`;
}

function displayHours(value: string) {
  return `${Number(value).toFixed(1)}h`;
}

function trackingCoverage(value: string) {
  const degraded = Number(value);
  if (!Number.isFinite(degraded)) return "unknown";
  return `${Math.max(0, 100 - degraded).toFixed(1)}%`;
}
