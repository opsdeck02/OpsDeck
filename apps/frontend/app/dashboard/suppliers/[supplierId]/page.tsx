import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SupplierEditForm } from "@/components/suppliers/supplier-controls";
import { getCurrentUser, getSupplierDetail } from "@/lib/api";
import { canAccessPilotAdmin } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function SupplierDetailPage({
  params,
}: {
  params: { supplierId: string };
}) {
  const [user, supplier] = await Promise.all([
    getCurrentUser(),
    getSupplierDetail(params.supplierId),
  ]);
  if (user?.is_superadmin) {
    redirect("/dashboard/superadmin");
  }
  if (!supplier) {
    notFound();
  }
  const role = user?.memberships[0]?.role;
  const canManage = canAccessPilotAdmin(role);

  return (
    <main className="space-y-4">
      <section className="od-panel px-4 py-5">
        <Link href="/dashboard/suppliers" className="text-sm font-semibold text-primary hover:underline">
          Back to reliability sources
        </Link>
        <div className="mt-3 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <Badge variant="outline">{supplier.code}</Badge>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight">{supplier.name}</h1>
            <p className="mt-2 text-sm text-mutedForeground">
              {supplier.primary_port ?? "No primary port"} · {supplier.country_of_origin ?? "Country not set"}
            </p>
            <p className="text-sm text-mutedForeground">
              Contact: {supplier.contact_name ?? "Not set"} {supplier.contact_email ? `(${supplier.contact_email})` : ""}
            </p>
          </div>
          <ReliabilityBadge
            grade={supplier.performance.reliability_grade}
            status={supplier.performance.reliability_status}
          />
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          ["Inbound events", String(supplier.performance.total_shipments)],
          ["Continuity reliability", displayPercent(supplier.performance.on_time_reliability_pct)],
          ["Avg delay", displayHours(supplier.performance.avg_eta_drift_hours)],
          ["Visibility coverage", trackingCoverage(supplier.performance.risk_signal_pct)],
          ["Active exposure links", String(supplier.performance.active_shipments)],
          ["Exposure value", displayCurrency(supplier.performance.total_value_at_risk)],
          ["Materials", supplier.performance.materials_supplied.join(", ") || "-"],
          ["Ports used", supplier.performance.ports_used.join(", ") || "-"],
        ].map(([label, value]) => (
          <Card key={label} className="bg-card/90 shadow-panel">
            <CardHeader>
              <CardTitle className="text-sm text-mutedForeground">{label}</CardTitle>
              <p className="mt-2 text-xl font-semibold">{value}</p>
            </CardHeader>
          </Card>
        ))}
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Edit reliability source</CardTitle>
        </CardHeader>
        <CardContent>
          <SupplierEditForm supplier={supplier} canManage={canManage} />
          {!canManage ? <p className="text-sm text-mutedForeground">Tenant admin access is required to edit reliability sources.</p> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Linked inbound dependencies</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="od-table-wrap">
            <table className="od-table min-w-[760px]">
              <thead>
                <tr>
                  <th>Inbound reference</th>
                  <th>Material</th>
                  <th>ETA</th>
                  <th>State</th>
                  <th>Signal reliability</th>
                </tr>
              </thead>
              <tbody>
                {supplier.linked_shipments.map((shipment) => (
                  <tr key={shipment.id}>
                    <td className="font-medium">
                      <Link href={`/dashboard/shipments/${shipment.shipment_id}`} className="text-primary hover:underline">
                        {shipment.shipment_id}
                      </Link>
                    </td>
                    <td>{shipment.material_name}</td>
                    <td>{formatDate(shipment.current_eta)}</td>
                    <td>{shipment.shipment_state.replace("_", " ")}</td>
                    <td>{shipment.confidence}</td>
                  </tr>
                ))}
                {supplier.linked_shipments.length === 0 ? (
                  <tr>
                    <td className="px-4 py-8 text-center text-mutedForeground" colSpan={5}>
                      No inbound dependencies are linked to this reliability source yet.
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

function ReliabilityBadge({
  grade,
  status,
}: {
  grade: string;
  status?: string;
}) {
  if (status === "uncalibrated") {
    return (
      <span className="rounded-full bg-slate-50 px-3 py-1.5 text-sm font-semibold text-slate-700 ring-1 ring-slate-200">
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
  return <span className={`rounded-full px-3 py-1.5 text-sm font-semibold ${className}`}>Grade {grade}</span>;
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

function displayCurrency(value: string) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
