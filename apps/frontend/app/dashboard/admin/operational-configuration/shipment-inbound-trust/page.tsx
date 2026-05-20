import { redirect } from "next/navigation";

import { ShipmentInboundTrustConfigForm } from "@/components/admin/shipment-inbound-trust-config-form";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { getCurrentUser, getStockCoverSummary } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ShipmentInboundTrustPage() {
  const [user, stockSummary] = await Promise.all([
    getCurrentUser(),
    getStockCoverSummary(),
  ]);
  if (!user) redirect("/login");
  if (user.memberships[0]?.role !== "tenant_admin")
    redirect("/dashboard/admin");

  const contexts = (stockSummary?.rows ?? []).map((row) => ({
    plant_id: row.plant_id,
    plant_code: row.plant_code,
    plant_name: row.plant_name,
    material_id: row.material_id,
    material_code: row.material_code,
    material_name: row.material_name,
  }));

  return (
    <div className="grid gap-4">
      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Shipment & Inbound Trust</CardTitle>
          <p className="max-w-3xl text-sm leading-5 text-mutedForeground">
            Configure expected visibility and ETA behavior so OpsDeck does not
            overreact to normal shipment update gaps.
          </p>
        </CardHeader>
      </Card>

      <ShipmentInboundTrustConfigForm contexts={contexts} />
    </div>
  );
}
