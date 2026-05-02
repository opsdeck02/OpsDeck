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
      headers={["Shipment", "Plant", "Material", "Port status", "Waiting", "Freshness", "Confidence"]}
      rows={portRows.map((row) => [
        <Link key={`${row.shipment_id}-link`} href={`/dashboard/shipments/${row.shipment_id}`} className="text-primary hover:underline">
          {row.shipment_id}
        </Link>,
        row.plant_name,
        row.material_name,
        stateBadge(row.port_status, row.likely_port_delay),
        `${Number(row.waiting_time_days).toFixed(2)} d`,
        freshnessBadge(row.freshness.freshness_label),
        <Badge key={`${row.shipment_id}-confidence`} variant="outline">
          {row.confidence}
        </Badge>,
      ])}
      empty="No port-monitoring records matched the current filters."
    />
  );
  const inlandTable = (
    <MonitoringTable
      headers={["Shipment", "Plant", "Material", "Dispatch status", "Expected arrival", "Freshness", "Confidence"]}
      rows={inlandRows.map((row) => [
        <Link key={`${row.shipment_id}-link`} href={`/dashboard/shipments/${row.shipment_id}`} className="text-primary hover:underline">
          {row.shipment_id}
        </Link>,
        row.plant_name,
        row.material_name,
        stateBadge(row.dispatch_status, row.inland_delay_flag),
        formatDate(row.expected_arrival),
        freshnessBadge(row.freshness.freshness_label),
        <Badge key={`${row.shipment_id}-confidence`} variant="outline">
          {row.confidence}
        </Badge>,
      ])}
      empty="No inland-monitoring records matched the current filters."
    />
  );

  return (
    <div className="grid gap-5">
      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Port and inland monitoring</CardTitle>
          <p className="text-sm text-mutedForeground">
            Trace what happened after port arrival, how delayed it looks, and how trustworthy each signal is.
          </p>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <input
              type="text"
              name="shipment_id"
              defaultValue={searchParams?.shipment_id ?? ""}
              placeholder="Shipment ID or vessel"
              className="rounded-2xl border bg-card px-4 py-3 text-sm"
            />
            <input
              type="number"
              name="plant_id"
              defaultValue={searchParams?.plant_id ?? ""}
              placeholder="Plant ID"
              className="rounded-2xl border bg-card px-4 py-3 text-sm"
            />
            <input
              type="number"
              name="material_id"
              defaultValue={searchParams?.material_id ?? ""}
              placeholder="Material ID"
              className="rounded-2xl border bg-card px-4 py-3 text-sm"
            />
            <select
              name="confidence"
              defaultValue={searchParams?.confidence ?? ""}
              className="rounded-2xl border bg-card px-4 py-3 text-sm"
            >
              <option value="">All confidence</option>
              <option value="high">high</option>
              <option value="medium">medium</option>
              <option value="low">low</option>
            </select>
            <label className="flex items-center gap-2 rounded-2xl border px-4 py-3 text-sm">
              <input type="checkbox" name="delayed_only" value="true" defaultChecked={filters.delayed_only} />
              <span>Delayed only</span>
            </label>
            <button
              type="submit"
              className="rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-primaryForeground"
            >
              Apply
            </button>
          </form>
        </CardContent>
      </Card>

      {detail ? (
        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Combined movement detail</CardTitle>
            <p className="text-sm text-mutedForeground">
              {detail.shipment.shipment_id} is currently evaluated with {detail.overall_confidence} confidence.
            </p>
          </CardHeader>
          <CardContent className="grid gap-5 lg:grid-cols-3">
            <SummaryBlock
              title="Shipment"
              primary={detail.shipment.shipment_state.replaceAll("_", " ")}
              subtext={`${detail.shipment.plant_name} · ${detail.shipment.material_name}`}
              confidence={detail.overall_confidence}
              notes={detail.progress_notes}
            />
            <SummaryBlock
              title="Port"
              primary={detail.port_summary?.port_status.replaceAll("_", " ") ?? "No port feed"}
              subtext={detail.port_summary?.freshness.freshness_label ?? "unknown"}
              confidence={detail.port_summary?.confidence ?? "low"}
              notes={
                detail.port_summary?.confidence_reasons ?? ["No port movement records are available."]
              }
            />
            <SummaryBlock
              title="Inland"
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
                <p className="text-sm font-medium">Missing signals</p>
                <div className="mt-3 space-y-2 text-sm text-mutedForeground">
                  {detail.missing_signals.map((note) => (
                    <div key={note} className="rounded-xl border border-dashed px-4 py-3">
                      {note}
                    </div>
                  ))}
                  {detail.missing_signals.length === 0 ? (
                    <div className="rounded-xl border border-dashed px-4 py-3">
                      No obvious movement gaps are currently flagged.
                    </div>
                  ) : null}
                </div>
              </div>
              <div>
                <p className="text-sm font-medium">Latest freshness</p>
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
        <Card className="bg-card/90 shadow-panel">
          <CardHeader className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <CardTitle>{activeView === "port" ? "Port view" : "Inland view"}</CardTitle>
              <p className="mt-1 text-sm text-mutedForeground">
                Full-page monitoring table. Scroll sideways if all columns do not fit on screen.
              </p>
            </div>
            <Link className="rounded-2xl border px-4 py-2 text-sm font-medium" href={combinedViewHref}>
              Back to combined view
            </Link>
          </CardHeader>
          <CardContent>{activeView === "port" ? portTable : inlandTable}</CardContent>
        </Card>
      ) : (
        <div className="grid gap-5 xl:grid-cols-2">
          <Card className="bg-card/90 shadow-panel">
            <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle>
                <Link href={portViewHref} className="hover:text-primary hover:underline">
                  Port view
                </Link>
              </CardTitle>
              <Link className="rounded-2xl border px-3 py-2 text-xs font-semibold" href={portViewHref}>
                Open full page
              </Link>
            </CardHeader>
            <CardContent>{portTable}</CardContent>
          </Card>

          <Card className="bg-card/90 shadow-panel">
            <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle>
                <Link href={inlandViewHref} className="hover:text-primary hover:underline">
                  Inland view
                </Link>
              </CardTitle>
              <Link className="rounded-2xl border px-3 py-2 text-xs font-semibold" href={inlandViewHref}>
                Open full page
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
    <div className="rounded-2xl border bg-card p-4 text-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="font-semibold">{title}</p>
        <Badge variant="outline">{confidence}</Badge>
      </div>
      <p className="mt-3 text-lg font-semibold">{primary}</p>
      <p className="mt-1 text-mutedForeground">{subtext}</p>
      <div className="mt-3 space-y-2 text-mutedForeground">
        {notes.slice(0, 3).map((note) => (
          <div key={note} className="rounded-xl bg-muted px-3 py-2">
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
    <div className="overflow-x-auto rounded-2xl border">
      <table className="min-w-[960px] w-full text-left text-sm">
        <thead className="bg-muted text-mutedForeground">
          <tr>
            {headers.map((header) => (
              <th key={header} className="whitespace-nowrap px-4 py-3 font-medium">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-t bg-card">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="whitespace-nowrap px-4 py-3">
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
    ? "border-accent bg-muted text-primary"
    : "border-sky-200 bg-sky-50 text-sky-700";
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${className}`}>
      {label.replaceAll("_", " ")}
    </span>
  );
}

function freshnessBadge(label: string) {
  const className =
    label === "fresh"
      ? "border-accent bg-muted text-accent"
      : label === "aging"
        ? "border-accent bg-muted text-primary"
        : "border bg-card text-mutedForeground";
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${className}`}>
      {label}
    </span>
  );
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
