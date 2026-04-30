import { redirect } from "next/navigation";
import Link from "next/link";

import { UploadPanel } from "@/components/onboarding/upload-panel";
import { Badge } from "@/components/ui/badge";
import { getCurrentUser, getMicrosoftConnections, getMicrosoftDataSources } from "@/lib/api";
import { canManageOperationalWorkflow } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function OnboardingPage() {
  const user = await getCurrentUser();
  const role = user?.memberships[0]?.role;
  if (!canManageOperationalWorkflow(role)) {
    redirect("/dashboard");
  }

  const [connections, sources] = await Promise.all([
    getMicrosoftConnections(),
    getMicrosoftDataSources(),
  ]);

  return (
    <div className="grid gap-5">
      <section className="rounded-md border bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm uppercase tracking-[0.18em] text-mutedForeground">Auto-sync</p>
            <h1 className="text-2xl font-semibold">Microsoft 365</h1>
            <p className="mt-2 text-sm text-mutedForeground">
              Connect OneDrive or SharePoint files for scheduled Graph API sync.
            </p>
          </div>
          <Link className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground" href="/dashboard/onboarding/microsoft">
            Set up Microsoft
          </Link>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <StatusBlock label="Connected accounts" value={connections.length} status={connections.some((item) => item.auth_error) ? "Reconnect required" : "Ready"} />
          <StatusBlock label="Active data sources" value={sources.filter((item) => item.is_active).length} status={sources.find((item) => item.sync_status === "auth_error")?.sync_status ?? sources[0]?.sync_status ?? "idle"} />
        </div>
      </section>
      <UploadPanel />
    </div>
  );
}

function StatusBlock({ label, value, status }: { label: string; value: number; status: string }) {
  const variant = status === "success" || status === "Ready" ? "default" : "outline";
  return (
    <div className="rounded-md border bg-background p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-mutedForeground">{label}</p>
        <Badge variant={variant}>{status}</Badge>
      </div>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
    </div>
  );
}
