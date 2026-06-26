import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { TenantHealthPanel } from "@/components/admin/customer-health-panel";
import { OperationalHistoryPanel } from "@/components/admin/operational-history-panel";
import { Badge } from "@/components/ui/badge";
import {
  getCurrentUser,
  getCustomerHealth,
  getOperationalHistoryReports,
  getOperationalHistorySummary,
  getTenantDetails,
  getWeeklyReviews,
} from "@/lib/api";
import { canAccessSuperadmin } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function SuperadminTenantDetailPage({
  params,
}: {
  params: { tenantId: string };
}) {
  const user = await getCurrentUser();
  if (!user || !canAccessSuperadmin(user)) redirect("/dashboard");

  const tenantId = Number(params.tenantId);
  if (!Number.isFinite(tenantId)) notFound();

  const [tenant, history, reports, weeklyReviews, health] = await Promise.all([
    getTenantDetails(tenantId),
    getOperationalHistorySummary(tenantId),
    getOperationalHistoryReports(tenantId),
    getWeeklyReviews(tenantId),
    getCustomerHealth(tenantId),
  ]);
  if (!tenant || !history || !health) notFound();

  return (
    <div className="grid gap-6">
      <div>
        <Link href="/dashboard/superadmin" className="text-sm font-semibold text-primary">
          Back to tenant portfolio
        </Link>
      </div>

      <section className="rounded-3xl border bg-card/90 p-6 shadow-panel">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-mutedForeground">
              Superadmin tenant profile
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">{tenant.name}</h1>
            <p className="mt-2 text-sm text-mutedForeground">
              {tenant.slug} · {tenant.plan_tier} plan · Created{" "}
              {new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(
                new Date(tenant.created_at),
              )}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={tenant.is_active ? "default" : "outline"}>
              {tenant.is_active ? "Active" : "Inactive"}
            </Badge>
            {tenant.is_demo_tenant ? <Badge variant="outline">Demo tenant</Badge> : null}
          </div>
        </div>
      </section>

      <TenantHealthPanel health={health} />

      <section className="rounded-3xl border bg-card/90 p-6 shadow-panel">
        <div className="mb-5">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-mutedForeground">
            Operational History
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight">
            Pilot and review record
          </h2>
        </div>
        <OperationalHistoryPanel
          tenantId={tenantId}
          initialSummary={history}
          initialReports={reports}
          initialWeeklyReviews={weeklyReviews}
        />
      </section>
    </div>
  );
}
