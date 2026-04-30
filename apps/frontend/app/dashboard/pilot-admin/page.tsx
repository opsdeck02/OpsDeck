import { redirect } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getCurrentUser, getMicrosoftConnections, getMicrosoftDataSources, getPilotReadiness } from "@/lib/api";
import { canAccessPilotAdmin } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function PilotAdminPage() {
  const user = await getCurrentUser();
  const role = user?.memberships[0]?.role;
  if (!canAccessPilotAdmin(role)) {
    redirect("/dashboard");
  }

  const [readiness, microsoftConnections, microsoftSources] = await Promise.all([
    getPilotReadiness(),
    getMicrosoftConnections(),
    getMicrosoftDataSources(),
  ]);

  return (
    <div className="grid gap-5">
      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Pilot readiness checklist</CardTitle>
          <p className="text-sm text-mutedForeground">
            Tenant-level implementation view for onboarding progress, data freshness, and go-live readiness.
          </p>
        </CardHeader>
        <CardContent className="text-sm text-mutedForeground">
          {readiness ? (
            <>Active tenant: {readiness.tenant}</>
          ) : (
            <>Pilot readiness data could not be loaded right now.</>
          )}
        </CardContent>
      </Card>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <Kpi label="Uploaded files" value={readiness?.counts.uploaded_files ?? 0} />
        <Kpi label="Ingestion jobs" value={readiness?.counts.ingestion_jobs ?? 0} />
        <Kpi label="Stock-cover rows" value={readiness?.counts.stock_cover_rows ?? 0} />
        <Kpi label="Open exceptions" value={readiness?.counts.open_exceptions ?? 0} />
        <Kpi label="Stale signals" value={readiness?.counts.stale_signals ?? 0} />
      </section>

      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Microsoft connection status</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm md:grid-cols-3">
          <StatusLine label="Connected accounts" value={microsoftConnections.length} ready={microsoftConnections.some((item) => item.is_active)} />
          <StatusLine label="Active Graph sources" value={microsoftSources.filter((item) => item.is_active).length} ready={microsoftSources.some((item) => item.sync_status === "success")} />
          <StatusLine label="Reconnect required" value={microsoftConnections.filter((item) => item.auth_error).length + microsoftSources.filter((item) => item.sync_status === "auth_error").length} ready={!microsoftConnections.some((item) => item.auth_error) && !microsoftSources.some((item) => item.sync_status === "auth_error")} />
        </CardContent>
      </Card>

      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Checklist</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {(readiness?.checks ?? []).map((check) => (
            <div key={check.key} className="rounded-2xl border bg-card p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="font-semibold">{check.label}</p>
                <Badge variant={check.ready ? "default" : "outline"}>
                  {check.ready ? "ready" : "attention"}
                </Badge>
              </div>
              <p className="mt-2 text-sm text-mutedForeground">{check.detail}</p>
              <p className="mt-2 text-xs text-mutedForeground">
                Last updated: {formatDate(check.last_updated_at)}
              </p>
            </div>
          ))}
          {(readiness?.checks ?? []).length === 0 ? (
            <p className="text-sm text-mutedForeground">
              No readiness checks are available yet for this tenant.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <section className="grid gap-5 lg:grid-cols-2">
        <TimestampCard
          title="Key timestamps"
          items={[
            ["Last upload", readiness?.last_upload_at ?? null],
            ["Last stock refresh", readiness?.last_stock_update_at ?? null],
            ["Last exception update", readiness?.last_exception_update_at ?? null],
            ["Last movement update", readiness?.last_movement_update_at ?? null],
          ]}
        />
        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Go-live prompt</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-mutedForeground">
            <p>1. Upload onboarding files and confirm ingestion counts look right.</p>
            <p>2. Confirm stock-cover rows exist and critical/warning risks are understandable.</p>
            <p>3. Run exception evaluation and assign owners for live pilot issues.</p>
            <p>4. Review the executive dashboard before customer steering calls.</p>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <CardTitle className="text-sm font-medium text-mutedForeground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-semibold tracking-tight">{value}</p>
      </CardContent>
    </Card>
  );
}

function StatusLine({ label, value, ready }: { label: string; value: number; ready: boolean }) {
  return (
    <div className="rounded-xl bg-muted px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <p className="font-medium">{label}</p>
        <Badge variant={ready ? "default" : "outline"}>{ready ? "ready" : "attention"}</Badge>
      </div>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function TimestampCard({
  title,
  items,
}: {
  title: string;
  items: Array<[string, string | null]>;
}) {
  return (
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {items.map(([label, value]) => (
          <div key={label} className="rounded-xl bg-muted px-4 py-3">
            <p className="font-medium">{label}</p>
            <p className="mt-2 text-mutedForeground">{formatDate(value)}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function formatDate(value: string | null) {
  if (!value) {
    return "Not available yet";
  }

  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
