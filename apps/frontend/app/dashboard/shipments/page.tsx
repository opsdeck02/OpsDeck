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
    <div className="grid gap-5">
      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Shipment visibility</CardTitle>
          <p className="text-sm text-mutedForeground">
            Tenant-scoped inbound shipments with derived state, confidence, and latest source.
          </p>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-[220px_1fr_auto]">
            <select
              name="state"
              defaultValue={searchParams?.state ?? ""}
              className="rounded-2xl border bg-card px-4 py-3 text-sm"
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
              placeholder="Search shipment ID or vessel"
              className="rounded-2xl border bg-card px-4 py-3 text-sm"
            />
            <button
              type="submit"
              className="rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-primaryForeground"
            >
              Apply
            </button>
          </form>
        </CardContent>
      </Card>

      <Card className="bg-card/90 shadow-panel">
        <CardContent className="pt-6">
          <div className="overflow-hidden rounded-2xl border">
            <table className="w-full text-left text-sm">
              <thead className="bg-muted text-mutedForeground">
                <tr>
                  <th className="px-4 py-3 font-medium">Shipment</th>
                  <th className="px-4 py-3 font-medium">Plant</th>
                  <th className="px-4 py-3 font-medium">Material</th>
                  <th className="px-4 py-3 font-medium">Quantity</th>
                  <th className="px-4 py-3 font-medium">Vessel</th>
                  <th className="px-4 py-3 font-medium">ETA</th>
                  <th className="px-4 py-3 font-medium">State</th>
                  <th className="px-4 py-3 font-medium">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {shipments.map((shipment) => (
                  <tr key={shipment.id} className="border-t bg-card">
                    <td className="px-4 py-3 font-medium">
                      <Link
                        href={`/dashboard/shipments/${shipment.shipment_id}`}
                        className="text-primary hover:underline"
                      >
                        {shipment.shipment_id}
                      </Link>
                    </td>
                    <td className="px-4 py-3">{shipment.plant_name}</td>
                    <td className="px-4 py-3">{shipment.material_name}</td>
                    <td className="px-4 py-3">{Number(shipment.quantity_mt).toLocaleString()} MT</td>
                    <td className="px-4 py-3">{shipment.vessel_name ?? "—"}</td>
                    <td className="px-4 py-3">{formatDate(shipment.current_eta)}</td>
                    <td className="px-4 py-3">
                      <StateBadge state={shipment.shipment_state} />
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant="outline">{shipment.confidence}</Badge>
                    </td>
                  </tr>
                ))}
                {shipments.length === 0 ? (
                  <tr>
                    <td className="px-4 py-8 text-center text-mutedForeground" colSpan={8}>
                      No shipments matched the current filters.
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
      ? "border bg-card text-mutedForeground"
      : state === "delivered"
        ? "border-accent bg-muted text-accent"
        : state === "discharging"
          ? "border-sky-200 bg-sky-50 text-sky-700"
          : state === "at_port"
            ? "border-accent bg-muted text-primary"
            : "border-accent bg-muted text-accent";
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${className}`}>
      {state.replace("_", " ")}
    </span>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
