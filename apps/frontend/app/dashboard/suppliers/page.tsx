import Link from "next/link";
import { redirect } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SupplierCreateForm } from "@/components/suppliers/supplier-controls";
import { getCurrentUser, getSuppliers } from "@/lib/api";
import { canAccessPilotAdmin } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function SuppliersPage() {
  const [user, suppliers] = await Promise.all([getCurrentUser(), getSuppliers()]);
  if (user?.is_superadmin) {
    redirect("/dashboard/superadmin");
  }
  const role = user?.memberships[0]?.role;
  const canManage = canAccessPilotAdmin(role);

  return (
    <main className="space-y-4">
      <section className="od-panel px-4 py-5">
        <div className="flex flex-col gap-2">
          <Badge variant="outline">Supplier intelligence</Badge>
          <h1 className="text-2xl font-semibold tracking-tight">Supplier exposure patterns</h1>
          <p className="text-sm text-mutedForeground">Delay history, tracking coverage, active inbound exposure.</p>
        </div>
      </section>

      <SupplierCreateForm canManage={canManage} />

      <Card>
        <CardHeader>
          <CardTitle>Suppliers</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="od-table-wrap">
            <table className="od-table min-w-[1040px]">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Primary Port</th>
                  <th>Materials</th>
                  <th>Reliability</th>
                  <th>On-Time</th>
                  <th>Avg delay</th>
                  <th>Tracking coverage</th>
                  <th>Active</th>
                  <th>Record</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((supplier) => (
                  <tr key={supplier.id}>
                    <td className="font-medium">
                      <Link href={`/dashboard/suppliers/${supplier.id}`} className="text-primary hover:underline">
                        {supplier.name}
                      </Link>
                    </td>
                    <td>{supplier.primary_port ?? "-"}</td>
                    <td>{supplier.performance.materials_supplied.join(", ") || "-"}</td>
                    <td><GradeBadge grade={supplier.performance.reliability_grade} /></td>
                    <td>{displayPercent(supplier.performance.on_time_reliability_pct)}</td>
                    <td>{displayHours(supplier.performance.avg_eta_drift_hours)}</td>
                    <td>{trackingCoverage(supplier.performance.risk_signal_pct)}</td>
                    <td>{supplier.performance.active_shipments}</td>
                    <td>
                      <Link href={`/dashboard/suppliers/${supplier.id}`} className="rounded-xl border px-3 py-2 text-xs font-semibold">
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
                {suppliers.length === 0 ? (
                  <tr>
                    <td className="px-4 py-8 text-center text-mutedForeground" colSpan={9}>
                      No suppliers have been created yet.
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

function GradeBadge({ grade }: { grade: string }) {
  const className =
    grade === "A"
      ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
      : grade === "B"
        ? "od-status-info"
        : grade === "C"
          ? "od-status-warning"
          : "od-status-critical";
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}>{grade}</span>;
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
