import { redirect } from "next/navigation";
import Link from "next/link";

import { UploadPanel } from "@/components/onboarding/upload-panel";
import { Badge } from "@/components/ui/badge";
import { getCurrentUser, getMicrosoftConnections, getMicrosoftDataSources, getTenantPlan } from "@/lib/api";
import { canManageOperationalWorkflow } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function OnboardingPage() {
  const user = await getCurrentUser();
  const role = user?.memberships[0]?.role;
  if (!canManageOperationalWorkflow(role)) {
    redirect("/dashboard");
  }

  const tenantPlan = await getTenantPlan();
  const automatedSourcesEnabled = tenantPlan?.capabilities.automated_data_sources ?? false;
  const [connections, sources] = automatedSourcesEnabled
    ? await Promise.all([getMicrosoftConnections(), getMicrosoftDataSources()])
    : [[], []];

  return (
    <div className="grid gap-4">
      {automatedSourcesEnabled ? (
        <section className="od-panel p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-mutedForeground">Continuity signal activation</p>
              <h1 className="text-xl font-semibold">Operational source health</h1>
            </div>
            <Link className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground" href="/dashboard/onboarding/microsoft">
              Set up Microsoft
            </Link>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <StatusBlock label="Connected sources" value={connections.length} status={connections.some((item) => item.auth_error) ? "Reconnect required" : "Ready"} />
            <StatusBlock label="Active signal feeds" value={sources.filter((item) => item.is_active).length} status={sources.find((item) => item.sync_status === "auth_error")?.sync_status ?? sources[0]?.sync_status ?? "idle"} />
            <StatusBlock label="Degraded sources" value={sources.filter((item) => item.sync_status === "auth_error").length} status={sources.some((item) => item.sync_status === "auth_error") ? "danger" : "clear"} />
            <StatusBlock label="Trust quality" value={sources.filter((item) => item.is_active && item.sync_status !== "auth_error").length} status="watching" />
          </div>
        </section>
      ) : (
        <section className="od-panel p-4">
          <p className="text-sm font-semibold text-mutedForeground">Continuity signal activation</p>
          <h1 className="mt-1 text-xl font-semibold">Operational sources pending</h1>
          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <StatusBlock label="Inbound feed" value={0} status="manual" />
            <StatusBlock label="Inventory feed" value={0} status="manual" />
            <StatusBlock label="Visibility feed" value={0} status="inactive" />
            <StatusBlock label="Trust quality" value={0} status="unknown" />
          </div>
        </section>
      )}
      <UploadPanel automatedSourcesEnabled={automatedSourcesEnabled} />
    </div>
  );
}

function StatusBlock({ label, value, status }: { label: string; value: number; status: string }) {
  const variant = status === "success" || status === "Ready" || status === "clear" ? "default" : "outline";
  return (
    <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-900/5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-mutedForeground">{label}</p>
        <Badge variant={variant}>{status}</Badge>
      </div>
      <p className="mt-2 text-xl font-semibold">{value}</p>
    </div>
  );
}
