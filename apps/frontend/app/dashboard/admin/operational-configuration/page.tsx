import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowRight, Gauge } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getCurrentUser } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function OperationalConfigurationPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  if (user.memberships[0]?.role !== "tenant_admin")
    redirect("/dashboard/admin");

  return (
    <div className="grid gap-4">
      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Operational Configuration</CardTitle>
          <p className="text-sm text-mutedForeground">
            Configure tenant-scoped assumptions used by continuity intelligence
            calculations.
          </p>
        </CardHeader>
      </Card>

      <div className="grid gap-3 md:grid-cols-2">
        <Link
          href="/dashboard/admin/operational-configuration/interruption-impact"
          className="group rounded-2xl bg-card/90 shadow-panel ring-1 ring-slate-900/5 transition hover:-translate-y-0.5 hover:ring-primary/30"
        >
          <CardHeader className="flex flex-row items-start justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="rounded-lg bg-slate-100 p-2 text-slate-700">
                <Gauge className="h-4 w-4" />
              </span>
              <CardTitle>Risk Value / Interruption Impact</CardTitle>
            </div>
            <ArrowRight className="mt-1 h-4 w-4 text-mutedForeground transition group-hover:translate-x-0.5 group-hover:text-primary" />
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-5 text-mutedForeground">
              Configure production interruption impact assumptions used in
              operational risk calculations.
            </p>
          </CardContent>
        </Link>
      </div>
    </div>
  );
}
