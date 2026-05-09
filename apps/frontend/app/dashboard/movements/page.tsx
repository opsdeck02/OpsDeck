import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getInlandMonitoring, getMovementDetail, getPortMonitoring } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function MovementsPage({
  searchParams,
}: {
  searchParams?: {
    plant_id?: string;
    material_id?: string;
    shipment_id?: string;
    confidence?: string;
    delayed_only?: string;
    view?: string;
  };
}) {
  const filters = {
    plant_id: searchParams?.plant_id ? Number(searchParams.plant_id) : undefined,
    material_id: searchParams?.material_id ? Number(searchParams.material_id) : undefined,
    shipment_id: searchParams?.shipment_id,
    confidence: searchParams?.confidence,
    delayed_only: searchParams?.delayed_only === "true",
  };

  const [portRows, inlandRows, detail] = await Promise.all([
    getPortMonitoring(filters),
    getInlandMonitoring(filters),
    searchParams?.shipment_id ? getMovementDetail(searchParams.shipment_id) : Promise.resolve(null),
  ]);
  const activeView = searchParams?.view === "port" || searchParams?.view === "inland" ? searchParams.view : null;
  const portViewHref = buildMovementHref(searchParams, "port");
  const inlandViewHref = buildMovementHref(searchParams, "inland");
  const combinedViewHref = buildMovementHref(searchParams, null);
  const portTable = (
    <MonitoringTable
      headers={["Inbound ref", "Continuity path", "Node condition", "Waiting", "Freshness", "Trust"]}
      rows={portRows.map((row) => [
        <Link key={`${row.shipment_id}-link`} href={`/dashboard/shipments/${row.shipment_id}`} className="text-primary hover:underline">
          {row.shipment_id}
        </Link>,
        `${row.material_name} · ${row.plant_name}`,
        stateBadge(row.port_status, row.likely_port_delay),
        `${Number(row.waiting_time_days).toFixed(2)} d`,
        freshnessBadge(row.freshness.freshness_label),
        trustBadge(row.confidence),
      ])}
      empty="No continuity signal degradation matched the current filters."
    />
  );
  const inlandTable = (
    <MonitoringTable
      headers={["Inbound ref", "Continuity path", "Inland condition", "Expected arrival", "Freshness", "Trust"]}
      rows={inlandRows.map((row) => [
        <Link key={`${row.shipment_id}-link`} href={`/dashboard/shipments/${row.shipment_id}`} className="text-primary hover:underline">
          {row.shipment_id}
        </Link>,
        `${row.material_name} · ${row.plant_name}`,
        stateBadge(row.dispatch_status, row.inland_delay_flag),
        formatDate(row.expected_arrival),
        freshnessBadge(row.freshness.freshness_label),
        trustBadge(row.confidence),
      ])}
      empty="No inbound continuity degradation matched the current filters."
    />
  );

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Continuity signal degradation</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-2 md:grid-cols-[minmax(220px,1fr)_160px_auto]">
            <input
              type="text"
              name="shipment_id"
              defaultValue={searchParams?.shipment_id ?? ""}
              placeholder="Inbound reference or vessel"
              className="rounded-xl border bg-card px-3 py-2 text-sm"
            />
            <label className="flex items-center gap-2 rounded-xl bg-slate-50 px-3 py-2 text-sm ring-1 ring-slate-900/5">
              <input type="checkbox" name="delayed_only" value="true" defaultChecked={filters.delayed_only} />
              <span>Degraded only</span>
            </label>
            <button
              type="submit"
              className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground"
            >
              Scan
            </button>
          </form>
        </CardContent>
      </Card>

      {detail ? (
      <Card>
          <CardHeader>
            <CardTitle>{detail.shipment.shipment_id} continuity signal condition</CardTitle>
            <Badge variant="outline">{operationalTrustLabel(detail.overall_confidence)}</Badge>
          </CardHeader>
          <CardContent className="grid gap-4 lg:grid-cols-3">
            <SummaryBlock
              title="Inbound dependency"
              primary={detail.shipment.shipment_state.replaceAll("_", " ")}
              subtext={`${detail.shipment.plant_name} · ${detail.shipment.material_name}`}
              confidence={detail.overall_confidence}
              notes={detail.progress_notes}
            />
            <SummaryBlock
              title="Port signal"
              primary={detail.port_summary?.port_status.replaceAll("_", " ") ?? "No port feed"}
              subtext={detail.port_summary?.freshness.freshness_label ?? "unknown"}
              confidence={detail.port_summary?.confidence ?? "low"}
              notes={
                detail.port_summary?.confidence_reasons ?? ["No port movement records are available."]
              }
            />
            <SummaryBlock
              title="Inland signal"
              primary={
                detail.inland_summary?.dispatch_status.replaceAll("_", " ") ?? "No inland feed"
              }
              subtext={detail.inland_summary?.freshness.freshness_label ?? "unknown"}
              confidence={detail.inland_summary?.confidence ?? "low"}
              notes={
                detail.inland_summary?.confidence_reasons ?? [
                  "No inland movement records are available.",
                ]
              }
            />
          </CardContent>
          <CardContent className="pt-0">
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <p className="text-sm font-medium">Visibility degradation</p>
                <div className="mt-3 space-y-2 text-sm text-mutedForeground">
                  {detail.missing_signals.map((note) => (
                    <div key={note} className="rounded-xl border border-dashed px-4 py-3">
                      {note}
                    </div>
                  ))}
                  {detail.missing_signals.length === 0 ? (
                    <div className="rounded-xl border border-dashed px-4 py-3">
                      No obvious continuity visibility gaps are currently flagged.
                    </div>
                  ) : null}
                </div>
              </div>
              <div>
                <p className="text-sm font-medium">Latest signal freshness</p>
                <div className="mt-3 rounded-xl bg-muted px-4 py-3 text-sm">
                  <p>Label: {detail.overall_freshness.freshness_label}</p>
                  <p>Last update: {formatDate(detail.overall_freshness.last_updated_at)}</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {activeView ? (
        <Card>
          <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <CardTitle>{activeView === "port" ? "Port signal view" : "Inland signal view"}</CardTitle>
            </div>
            <Link className="rounded-xl bg-slate-50 px-3 py-2 text-sm font-medium ring-1 ring-slate-900/5" href={combinedViewHref}>
              Back to continuity signals
            </Link>
          </CardHeader>
          <CardContent>{activeView === "port" ? portTable : inlandTable}</CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          <Card>
            <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle>
                <Link href={portViewHref} className="hover:text-primary hover:underline">
                  Port degradation signals
                </Link>
              </CardTitle>
              <Link className="rounded-xl bg-slate-50 px-3 py-2 text-xs font-semibold ring-1 ring-slate-900/5" href={portViewHref}>
                Inspect signals
              </Link>
            </CardHeader>
            <CardContent>{portTable}</CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle>
                <Link href={inlandViewHref} className="hover:text-primary hover:underline">
                  Inland degradation signals
                </Link>
              </CardTitle>
              <Link className="rounded-xl bg-slate-50 px-3 py-2 text-xs font-semibold ring-1 ring-slate-900/5" href={inlandViewHref}>
                Inspect signals
              </Link>
            </CardHeader>
            <CardContent>{inlandTable}</CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

function SummaryBlock({
  title,
  primary,
  subtext,
  confidence,
  notes,
}: {
  title: string;
  primary: string;
  subtext: string;
  confidence: string;
  notes: string[];
}) {
  return (
    <div className="rounded-xl bg-slate-50 p-3 text-sm ring-1 ring-slate-900/5">
      <div className="flex items-center justify-between gap-3">
        <p className="font-semibold">{title}</p>
        {trustBadge(confidence)}
      </div>
      <p className="mt-2 text-base font-semibold">{primary}</p>
      <p className="mt-1 text-mutedForeground">{subtext}</p>
      <div className="mt-3 space-y-2 text-mutedForeground">
        {notes.slice(0, 3).map((note) => (
          <div key={note} className="rounded-xl bg-white px-3 py-2 ring-1 ring-slate-900/5">
            {note}
          </div>
        ))}
      </div>
    </div>
  );
}

function MonitoringTable({
  headers,
  rows,
  empty,
}: {
  headers: string[];
  rows: React.ReactNode[][];
  empty: string;
}) {
  return (
    <div className="od-table-wrap">
      <table className="od-table min-w-[920px]">
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="whitespace-nowrap">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
          {rows.length === 0 ? (
            <tr>
              <td className="px-4 py-8 text-center text-mutedForeground" colSpan={headers.length}>
                {empty}
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function stateBadge(label: string, delayed: boolean) {
  const className = delayed
    ? "od-status-warning"
    : "od-status-info";
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}>
      {label.replaceAll("_", " ")}
    </span>
  );
}

function freshnessBadge(label: string) {
  const className =
    label === "fresh"
      ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
      : label === "aging"
        ? "od-status-warning"
        : "od-status-passive";
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}>
      {label}
    </span>
  );
}

function trustBadge(confidence: string) {
  const label = operationalTrustLabel(confidence);
  const className =
    confidence === "high"
      ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
      : confidence === "medium"
        ? "od-status-warning"
        : "od-status-critical";
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}>
      {label}
    </span>
  );
}

function operationalTrustLabel(confidence: string) {
  if (confidence === "high") return "verified";
  if (confidence === "medium") return "incomplete";
  return "weak tracking";
}

function buildMovementHref(
  searchParams: {
    plant_id?: string;
    material_id?: string;
    shipment_id?: string;
    confidence?: string;
    delayed_only?: string;
    view?: string;
  } | undefined,
  view: "port" | "inland" | null,
) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams ?? {})) {
    if (key !== "view" && value) {
      params.set(key, value);
    }
  }
  if (view) {
    params.set("view", view);
  }
  const query = params.toString();
  return query ? `/dashboard/movements?${query}` : "/dashboard/movements";
}

function formatDate(value?: string | null) {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
