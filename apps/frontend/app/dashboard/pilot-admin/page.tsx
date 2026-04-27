import { redirect } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getCurrentUser, getPilotReadiness } from "@/lib/api";
import { canAccessPilotAdmin } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function PilotAdminPage() {
  const user = await getCurrentUser();
  const role = user?.memberships[0]?.role;
  if (!canAccessPilotAdmin(role)) {
    redirect("/dashboard");
  }

  const readiness = await getPilotReadiness();

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
