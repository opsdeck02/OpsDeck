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
    <main className="space-y-6">
      <section className="rounded-3xl border bg-card/90 px-6 py-6 shadow-panel">
        <div className="flex flex-col gap-2">
          <Badge variant="outline">Supplier master</Badge>
          <h1 className="text-3xl font-semibold tracking-tight">Supplier reliability memory</h1>
          <p className="text-sm text-mutedForeground">
            Supplier records compound shipment history, port preferences, material categories, and continuity risk signals.
          </p>
        </div>
      </section>

      <SupplierCreateForm canManage={canManage} />

      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Suppliers</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-hidden rounded-2xl border">
            <table className="w-full text-left text-sm">
              <thead className="bg-muted text-mutedForeground">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Primary Port</th>
                  <th className="px-4 py-3 font-medium">Materials</th>
                  <th className="px-4 py-3 font-medium">Reliability Grade</th>
                  <th className="px-4 py-3 font-medium">On-Time %</th>
                  <th className="px-4 py-3 font-medium">Avg ETA Drift</th>
                  <th className="px-4 py-3 font-medium">Risk Signal %</th>
                  <th className="px-4 py-3 font-medium">Active Shipments</th>
                  <th className="px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((supplier) => (
                  <tr key={supplier.id} className="border-t bg-card">
                    <td className="px-4 py-3 font-medium">
                      <Link href={`/dashboard/suppliers/${supplier.id}`} className="text-primary hover:underline">
                        {supplier.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3">{supplier.primary_port ?? "-"}</td>
                    <td className="px-4 py-3">{supplier.performance.materials_supplied.join(", ") || "-"}</td>
                    <td className="px-4 py-3"><GradeBadge grade={supplier.performance.reliability_grade} /></td>
                    <td className="px-4 py-3">{displayPercent(supplier.performance.on_time_reliability_pct)}</td>
                    <td className="px-4 py-3">{displayHours(supplier.performance.avg_eta_drift_hours)}</td>
                    <td className="px-4 py-3">{displayPercent(supplier.performance.risk_signal_pct)}</td>
                    <td className="px-4 py-3">{supplier.performance.active_shipments}</td>
                    <td className="px-4 py-3">
                      <Link href={`/dashboard/suppliers/${supplier.id}`} className="rounded-2xl border px-3 py-2 text-xs font-semibold">
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
      ? "border-accent bg-muted text-accent"
      : grade === "B"
        ? "border-accent bg-muted text-primary"
        : grade === "C"
          ? "border-accent bg-muted text-primary"
          : "border-accent bg-muted text-primary";
  return <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${className}`}>{grade}</span>;
}

function displayPercent(value: string) {
  return `${Number(value).toFixed(1)}%`;
}

function displayHours(value: string) {
  return `${Number(value).toFixed(1)}h`;
}
