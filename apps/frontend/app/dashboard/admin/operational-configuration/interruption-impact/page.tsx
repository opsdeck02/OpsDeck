import Link from "next/link";
import { redirect } from "next/navigation";

import { InterruptionImpactConfigForm } from "@/components/admin/interruption-impact-config-form";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { getCurrentUser, getStockCoverSummary } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function InterruptionImpactPage() {
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
          <Link
            href="/dashboard/admin/operational-configuration"
            className="text-xs font-semibold text-mutedForeground transition hover:text-foreground"
          >
            &larr; Back to Operational Configuration
          </Link>
          <CardTitle>Risk Value / Interruption Impact</CardTitle>
          <p className="max-w-3xl text-sm leading-5 text-mutedForeground">
            Configure production economics and continuity behavior assumptions
            used when OpsDeck calculates operational interruption impact for a
            plant/material context.
          </p>
        </CardHeader>
      </Card>

      <InterruptionImpactConfigForm contexts={contexts} />
    </div>
  );
}
