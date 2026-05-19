import { redirect } from "next/navigation";

import { ContinuityThresholdsConfigForm } from "@/components/admin/continuity-thresholds-config-form";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { getCurrentUser, getStockCoverSummary } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ContinuityThresholdsPage() {
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
          <CardTitle>Continuity Thresholds</CardTitle>
          <p className="max-w-3xl text-sm leading-5 text-mutedForeground">
            Define when a material becomes a warning, critical, or projected
            stockout risk for a specific plant-material combination.
          </p>
        </CardHeader>
      </Card>

      <ContinuityThresholdsConfigForm contexts={contexts} />
    </div>
  );
}
