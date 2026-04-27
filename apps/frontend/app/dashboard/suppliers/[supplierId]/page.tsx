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
    <main className="space-y-6">
      <section className="rounded-3xl border bg-card/90 px-6 py-6 shadow-panel">
        <Link href="/dashboard/suppliers" className="text-sm font-semibold text-primary hover:underline">
          Back to suppliers
        </Link>
        <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <Badge variant="outline">{supplier.code}</Badge>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight">{supplier.name}</h1>
            <p className="mt-2 text-sm text-mutedForeground">
              {supplier.primary_port ?? "No primary port"} · {supplier.country_of_origin ?? "Country not set"}
            </p>
            <p className="text-sm text-mutedForeground">
              Contact: {supplier.contact_name ?? "Not set"} {supplier.contact_email ? `(${supplier.contact_email})` : ""}
            </p>
          </div>
          <GradeBadge grade={supplier.performance.reliability_grade} />
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          ["Total shipments", String(supplier.performance.total_shipments)],
          ["On-time reliability", displayPercent(supplier.performance.on_time_reliability_pct)],
          ["Avg ETA drift", displayHours(supplier.performance.avg_eta_drift_hours)],
          ["Risk signal", displayPercent(supplier.performance.risk_signal_pct)],
          ["Active shipments", String(supplier.performance.active_shipments)],
          ["Value at risk", displayCurrency(supplier.performance.total_value_at_risk)],
          ["Materials", supplier.performance.materials_supplied.join(", ") || "-"],
          ["Ports used", supplier.performance.ports_used.join(", ") || "-"],
        ].map(([label, value]) => (
          <Card key={label} className="bg-card/90 shadow-panel">
            <CardHeader>
              <CardTitle className="text-sm text-mutedForeground">{label}</CardTitle>
              <p className="mt-2 text-2xl font-semibold">{value}</p>
            </CardHeader>
          </Card>
        ))}
      </section>

      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Edit supplier</CardTitle>
        </CardHeader>
        <CardContent>
          <SupplierEditForm supplier={supplier} canManage={canManage} />
          {!canManage ? <p className="text-sm text-mutedForeground">Tenant admin access is required to edit suppliers.</p> : null}
        </CardContent>
      </Card>

      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Linked shipments</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-hidden rounded-2xl border">
            <table className="w-full text-left text-sm">
              <thead className="bg-muted text-mutedForeground">
                <tr>
                  <th className="px-4 py-3 font-medium">Shipment</th>
                  <th className="px-4 py-3 font-medium">Material</th>
                  <th className="px-4 py-3 font-medium">ETA</th>
                  <th className="px-4 py-3 font-medium">State</th>
                  <th className="px-4 py-3 font-medium">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {supplier.linked_shipments.map((shipment) => (
                  <tr key={shipment.id} className="border-t bg-card">
                    <td className="px-4 py-3 font-medium">
                      <Link href={`/dashboard/shipments/${shipment.shipment_id}`} className="text-primary hover:underline">
                        {shipment.shipment_id}
                      </Link>
                    </td>
                    <td className="px-4 py-3">{shipment.material_name}</td>
                    <td className="px-4 py-3">{formatDate(shipment.current_eta)}</td>
                    <td className="px-4 py-3">{shipment.shipment_state.replace("_", " ")}</td>
                    <td className="px-4 py-3">{shipment.confidence}</td>
                  </tr>
                ))}
                {supplier.linked_shipments.length === 0 ? (
                  <tr>
                    <td className="px-4 py-8 text-center text-mutedForeground" colSpan={5}>
                      No shipments are linked to this supplier yet.
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
  return <span className={`rounded-full border px-4 py-2 text-sm font-semibold ${className}`}>Grade {grade}</span>;
}

function displayPercent(value: string) {
  return `${Number(value).toFixed(1)}%`;
}

function displayHours(value: string) {
  return `${Number(value).toFixed(1)}h`;
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
