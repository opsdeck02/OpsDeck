import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getShipments } from "@/lib/api";

export const dynamic = "force-dynamic";

const states = ["planned", "on_water", "at_port", "discharging", "in_transit", "delivered", "cancelled"];

export default async function ShipmentsPage({
  searchParams,
}: {
  searchParams?: { state?: string; search?: string };
}) {
  const shipments = await getShipments({
    state: searchParams?.state,
    search: searchParams?.search,
  });

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Inbound continuity</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-[220px_1fr_auto]">
            <select
              name="state"
              defaultValue={searchParams?.state ?? ""}
              className="rounded-xl border bg-card px-3 py-2.5 text-sm"
            >
              <option value="">All states</option>
              {states.map((state) => (
                <option key={state} value={state}>
                  {state.replace("_", " ")}
                </option>
              ))}
            </select>
            <input
              type="search"
              name="search"
              defaultValue={searchParams?.search ?? ""}
              placeholder="Search inbound reference or vessel"
              className="rounded-xl border bg-card px-3 py-2.5 text-sm"
            />
            <button
              type="submit"
              className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primaryForeground"
            >
              Apply
            </button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <div className="od-table-wrap">
            <table className="od-table min-w-[920px]">
              <thead>
                <tr>
                  <th>Inbound reference</th>
                  <th>Plant</th>
                  <th>Material</th>
                  <th>Quantity</th>
                  <th>Vessel</th>
                  <th>ETA</th>
                  <th>Continuity state</th>
                  <th>Signal trust</th>
                </tr>
              </thead>
              <tbody>
                {shipments.map((shipment) => (
                  <tr key={shipment.id}>
                    <td className="font-medium">
                      <Link
                        href={`/dashboard/shipments/${shipment.shipment_id}`}
                        className="text-primary hover:underline"
                      >
                        {shipment.shipment_id}
                      </Link>
                    </td>
                    <td>{shipment.plant_name}</td>
                    <td>{shipment.material_name}</td>
                    <td>{Number(shipment.quantity_mt).toLocaleString()} MT</td>
                    <td>{shipment.vessel_name ?? "—"}</td>
                    <td>{formatDate(shipment.current_eta)}</td>
                    <td>
                      <StateBadge state={shipment.shipment_state} />
                    </td>
                    <td>
                      <TrustBadge confidence={shipment.confidence} state={shipment.shipment_state} />
                    </td>
                  </tr>
                ))}
                {shipments.length === 0 ? (
                  <tr>
                    <td className="px-4 py-8 text-center text-mutedForeground" colSpan={8}>
                      Monitored inbound dependencies remain stable for the current filters.
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

function StateBadge({ state }: { state: string }) {
  const className =
    state === "cancelled"
      ? "od-status-passive"
      : state === "delivered"
        ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
      : state === "discharging"
          ? "od-status-warning"
          : state === "at_port"
            ? "od-status-warning"
            : "od-status-info";
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}>
      {state.replace("_", " ")}
    </span>
  );
}

function TrustBadge({ confidence, state }: { confidence: string; state: string }) {
  const degraded = ["at_port", "discharging", "cancelled"].includes(state);
  const label =
    degraded
      ? "degraded signal"
      : confidence === "high"
        ? "verified"
        : confidence === "medium"
          ? "incomplete"
          : "weak tracking";
  const className =
    label === "verified"
      ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
      : label === "incomplete"
        ? "od-status-warning"
        : "od-status-critical";
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}>{label}</span>;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
