import Link from "next/link";

import { ExceptionPageClient } from "@/components/exceptions/exception-page-client";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getCurrentUser, getExceptions, getTenantUsers } from "@/lib/api";
import { canManageOperationalWorkflow } from "@/lib/roles";

export const dynamic = "force-dynamic";

export default async function ExceptionsPage({
  searchParams,
}: {
  searchParams?: {
    status?: string;
    severity?: string;
    type?: string;
    owner_user_id?: string;
    unassigned_only?: string;
  };
}) {
  const [response, user] = await Promise.all([
    getExceptions({
      status: searchParams?.status,
      severity: searchParams?.severity,
      type: searchParams?.type,
      owner_user_id: searchParams?.owner_user_id ? Number(searchParams.owner_user_id) : undefined,
      unassigned_only: searchParams?.unassigned_only === "true",
    }),
    getCurrentUser(),
  ]);
  const canManage = canManageOperationalWorkflow(user?.memberships[0]?.role);
  const users = canManage ? await getTenantUsers() : [];

  const counts = response?.counts;
  const items = response?.items ?? [];
  const exportHref = `/api/exports/exceptions${buildExportQuery(searchParams)}`;

  return (
    <div className="grid gap-4">
      {!response ? (
        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Signals unavailable</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-mutedForeground">
            Signal data could not be loaded for this tenant right now. Retry once the API connection is back.
          </CardContent>
        </Card>
      ) : null}

      <section className="grid gap-3 md:grid-cols-4">
        <KpiCard label="Open continuity signals" value={counts?.open_exceptions ?? 0} />
        <KpiCard label="Critical exposure signals" value={counts?.critical_exceptions ?? 0} tone="critical" />
        <KpiCard label="Unowned signals" value={counts?.unassigned_exceptions ?? 0} tone="warning" />
        <KpiCard label="Resolved recently" value={counts?.resolved_recently ?? 0} />
      </section>

      <ExceptionPageClient
        users={users}
        initialFilters={searchParams ?? {}}
        canManage={canManage}
      />

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
          <CardTitle>Continuity signals</CardTitle>
            <a href={exportHref} className="rounded-xl border px-3 py-2 text-xs font-semibold">
              Export CSV
            </a>
          </div>
          <p className="text-sm text-mutedForeground">
            Deterministic tenant-scoped records created from inventory, inbound, and visibility signals.
          </p>
        </CardHeader>
        <CardContent>
          <div className="od-table-wrap">
            <table className="od-table min-w-[1040px]">
              <thead>
                <tr>
                  <th>Signal</th>
                  <th>Type</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Owner</th>
                  <th>Plant / material</th>
                  <th>Inbound ref</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td className="font-medium">
                      <Link href={`/dashboard/exceptions/${item.id}`} className="text-primary hover:underline">
                        {item.title}
                      </Link>
                    </td>
                    <td>{item.type.replaceAll("_", " ")}</td>
                    <td>
                      <SeverityBadge severity={item.severity} />
                    </td>
                    <td>
                      <StatusBadge status={item.status} />
                    </td>
                    <td>{item.current_owner?.full_name ?? "Unassigned"}</td>
                    <td>
                      {item.linked_plant?.label ?? "—"} / {item.linked_material?.label ?? "—"}
                    </td>
                    <td>{item.linked_shipment?.label ?? "—"}</td>
                    <td>{formatDate(item.updated_at)}</td>
                  </tr>
                ))}
                {items.length === 0 ? (
                  <tr>
                    <td className="px-4 py-8 text-center text-mutedForeground" colSpan={8}>
                      No continuity degradation signals matched the current filters.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function KpiCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: "default" | "critical" | "warning";
}) {
  const className =
    tone === "critical"
      ? "text-primary"
      : tone === "warning"
        ? "text-primary"
        : "text-foreground";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-mutedForeground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className={`text-2xl font-semibold tracking-tight ${className}`}>{value}</p>
      </CardContent>
    </Card>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const className =
    severity === "critical"
      ? "od-status-critical"
      : severity === "high"
        ? "od-status-warning"
        : severity === "medium"
          ? "od-status-info"
          : "od-status-passive";
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}>{severity}</span>;
}

function StatusBadge({ status }: { status: string }) {
  const variant = status === "resolved" || status === "closed" ? "outline" : "default";
  return <Badge variant={variant}>{status.replace("_", " ")}</Badge>;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function buildExportQuery(searchParams: {
  status?: string;
  severity?: string;
  type?: string;
  owner_user_id?: string;
  unassigned_only?: string;
} | undefined) {
  const query = new URLSearchParams();
  if (searchParams?.status) query.set("status", searchParams.status);
  if (searchParams?.severity) query.set("severity", searchParams.severity);
  if (searchParams?.type) query.set("type", searchParams.type);
  if (searchParams?.owner_user_id) query.set("owner_user_id", searchParams.owner_user_id);
  if (searchParams?.unassigned_only === "true") query.set("unassigned_only", "true");
  const suffix = query.toString();
  return suffix ? `?${suffix}` : "";
}
