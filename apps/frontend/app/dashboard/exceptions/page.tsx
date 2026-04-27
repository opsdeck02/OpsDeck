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
    <div className="grid gap-5">
      {!response ? (
        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Exceptions unavailable</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-mutedForeground">
            Exception data could not be loaded for this tenant right now. Retry once the API connection is back.
          </CardContent>
        </Card>
      ) : null}

      <section className="grid gap-4 md:grid-cols-4">
        <KpiCard label="Open exceptions" value={counts?.open_exceptions ?? 0} />
        <KpiCard label="Critical exceptions" value={counts?.critical_exceptions ?? 0} tone="critical" />
        <KpiCard label="Unassigned exceptions" value={counts?.unassigned_exceptions ?? 0} tone="warning" />
        <KpiCard label="Resolved recently" value={counts?.resolved_recently ?? 0} />
      </section>

      <ExceptionPageClient
        users={users}
        initialFilters={searchParams ?? {}}
        canManage={canManage}
      />

      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle>Exception workflow</CardTitle>
            <a href={exportHref} className="rounded-2xl border px-4 py-2 text-xs font-semibold">
              Export CSV
            </a>
          </div>
          <p className="text-sm text-mutedForeground">
            Deterministic tenant-scoped cases created from stock, shipment, and inland risk signals.
          </p>
        </CardHeader>
        <CardContent>
          <div className="overflow-hidden rounded-2xl border">
            <table className="w-full text-left text-sm">
              <thead className="bg-muted text-mutedForeground">
                <tr>
                  <th className="px-4 py-3 font-medium">Exception</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Severity</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Owner</th>
                  <th className="px-4 py-3 font-medium">Plant / material</th>
                  <th className="px-4 py-3 font-medium">Shipment</th>
                  <th className="px-4 py-3 font-medium">Updated</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-t bg-card">
                    <td className="px-4 py-3 font-medium">
                      <Link href={`/dashboard/exceptions/${item.id}`} className="text-primary hover:underline">
                        {item.title}
                      </Link>
                    </td>
                    <td className="px-4 py-3">{item.type.replaceAll("_", " ")}</td>
                    <td className="px-4 py-3">
                      <SeverityBadge severity={item.severity} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="px-4 py-3">{item.current_owner?.full_name ?? "Unassigned"}</td>
                    <td className="px-4 py-3">
                      {item.linked_plant?.label ?? "—"} / {item.linked_material?.label ?? "—"}
                    </td>
                    <td className="px-4 py-3">{item.linked_shipment?.label ?? "—"}</td>
                    <td className="px-4 py-3">{formatDate(item.updated_at)}</td>
                  </tr>
                ))}
                {items.length === 0 ? (
                  <tr>
                    <td className="px-4 py-8 text-center text-mutedForeground" colSpan={8}>
                      No exceptions matched the current filters. Use “Evaluate exceptions” to refresh cases.
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
    <Card className="bg-card/90 shadow-panel">
      <CardHeader>
        <CardTitle className="text-sm font-medium text-mutedForeground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className={`text-3xl font-semibold tracking-tight ${className}`}>{value}</p>
      </CardContent>
    </Card>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const className =
    severity === "critical"
      ? "border-accent bg-muted text-primary"
      : severity === "high"
        ? "border-accent bg-muted text-primary"
        : severity === "medium"
          ? "border-sky-200 bg-sky-50 text-sky-700"
          : "border bg-card text-mutedForeground";
  return <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${className}`}>{severity}</span>;
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
