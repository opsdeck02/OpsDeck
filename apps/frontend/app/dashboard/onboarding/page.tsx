import { redirect } from "next/navigation";
import Link from "next/link";
import type { PilotReadinessResponse, PilotSetupChecklistItem } from "@steelops/contracts";

import { UploadPanel } from "@/components/onboarding/upload-panel";
import { Badge } from "@/components/ui/badge";
import {
  getCurrentUser,
  getMicrosoftConnections,
  getMicrosoftDataSources,
  getPilotReadiness,
  getTenantPlan,
} from "@/lib/api";
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
  const canClearUploadedData = role === "tenant_admin" || user?.is_superadmin;
  const [connections, sources] = automatedSourcesEnabled
    ? await Promise.all([getMicrosoftConnections(), getMicrosoftDataSources()])
    : [[], []];
  const readiness = await getPilotReadiness();

  return (
    <div className="grid gap-4">
      {readiness ? <PilotSetupChecklist readiness={readiness} /> : null}
      {automatedSourcesEnabled ? (
        <section className="od-panel p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-mutedForeground">Continuity signal activation</p>
              <h1 className="text-xl font-semibold">Upload Center</h1>
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
          <h1 className="mt-1 text-xl font-semibold">Upload Center</h1>
          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <StatusBlock label="Inbound feed" value={0} status="manual" />
            <StatusBlock label="Inventory feed" value={0} status="manual" />
            <StatusBlock label="Visibility feed" value={0} status="inactive" />
            <StatusBlock label="Trust quality" value={0} status="unknown" />
          </div>
        </section>
      )}
      <UploadPanel
        automatedSourcesEnabled={automatedSourcesEnabled}
        canClearUploadedData={canClearUploadedData}
      />
    </div>
  );
}

function PilotSetupChecklist({ readiness }: { readiness: PilotReadinessResponse }) {
  const mandatory = readiness.setup_checklist.filter((item) => item.category === "mandatory");
  const recommended = readiness.setup_checklist.filter((item) => item.category === "recommended");
  const optional = readiness.setup_checklist.filter((item) => item.category === "optional");
  return (
    <section className="od-panel p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-mutedForeground">Guided pilot setup</p>
          <h1 className="mt-1 text-xl font-semibold">Pilot Setup Checklist</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-mutedForeground">
            Follow this path before making strong continuity claims: upload stock, confirm
            consumption, upload shipments with ETA, upload thresholds, review rejected rows,
            then review newly created master data.
          </p>
        </div>
        <Badge variant={readiness.safe_to_rely_on ? "default" : "outline"}>
          {readiness.setup_status}
        </Badge>
      </div>
      {!readiness.safe_to_rely_on ? (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900">
          Pilot setup is incomplete. Treat these results as preliminary until required data is
          reviewed. {readiness.safe_to_rely_on_reason}
        </div>
      ) : (
        <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm font-medium text-emerald-900">
          Pilot setup is ready for guided review.
        </div>
      )}
      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <ChecklistGroup title="Mandatory" items={mandatory} />
        <ChecklistGroup title="Recommended" items={recommended} />
        <ChecklistGroup title="Optional" items={optional} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-sm">
        <Link className="font-semibold text-primary hover:underline" href="/dashboard/risk-workspace">
          Open Risk Workspace
        </Link>
        <span className="text-mutedForeground">/</span>
        <Link className="font-semibold text-primary hover:underline" href="/dashboard/admin/past-incident-analysis">
          Past Incident Analysis
        </Link>
        <span className="text-mutedForeground">/</span>
        <Link className="font-semibold text-primary hover:underline" href="/dashboard/admin/executive-continuity-report">
          Executive Continuity Report
        </Link>
      </div>
    </section>
  );
}

function ChecklistGroup({ title, items }: { title: string; items: PilotSetupChecklistItem[] }) {
  return (
    <div className="grid content-start gap-2">
      <h2 className="text-sm font-semibold text-mutedForeground">{title}</h2>
      {items.map((item) => (
        <ChecklistRow key={item.key} item={item} />
      ))}
    </div>
  );
}

function ChecklistRow({ item }: { item: PilotSetupChecklistItem }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-900/5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold text-slate-900">{item.label}</p>
          <p className="mt-1 text-sm leading-5 text-mutedForeground">{item.detail}</p>
        </div>
        <Badge variant={checklistBadgeVariant(item.state)}>{item.state}</Badge>
      </div>
      {item.state !== "Complete" ? (
        <p className="mt-2 text-sm leading-5 text-slate-700">{item.next_action}</p>
      ) : null}
      <Link className="mt-2 inline-flex text-sm font-semibold text-primary hover:underline" href={item.href}>
        Open
      </Link>
    </div>
  );
}

function checklistBadgeVariant(state: string) {
  if (state === "Complete") return "default";
  return "outline";
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
