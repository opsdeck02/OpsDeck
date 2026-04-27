import { notFound } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getShipmentDetail } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ShipmentDetailPage({
  params,
}: {
  params: { shipmentId: string };
}) {
  const detail = await getShipmentDetail(params.shipmentId);
  if (!detail) {
    notFound();
  }

  return (
    <div className="grid gap-5">
      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>{detail.shipment.shipment_id}</CardTitle>
          <div className="flex flex-wrap items-center gap-3 text-sm text-mutedForeground">
            <span>{detail.shipment.plant_name}</span>
            <span>{detail.shipment.material_name}</span>
            <Badge variant="outline">{detail.shipment.shipment_state.replace("_", " ")}</Badge>
            <Badge variant="outline">{detail.shipment.confidence}</Badge>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Metric label="Quantity" value={`${Number(detail.shipment.quantity_mt).toLocaleString()} MT`} />
          <Metric label="Current ETA" value={formatDate(detail.shipment.current_eta)} />
          <Metric label="Latest source" value={detail.shipment.latest_status_source} />
          <Metric label="Last update" value={formatDate(detail.shipment.last_update_at)} />
        </CardContent>
      </Card>

      <div className="grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Shipment summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <Line label="Supplier" value={detail.supplier_name} />
            <Line label="Vessel" value={detail.shipment.vessel_name ?? "—"} />
            <Line label="Origin port" value={detail.shipment.origin_port ?? "—"} />
            <Line label="Destination port" value={detail.shipment.destination_port ?? "—"} />
            <Line label="IMO" value={detail.imo_number ?? "—"} />
            <Line label="MMSI" value={detail.mmsi ?? "—"} />
            <Line label="Planned ETA" value={formatDate(detail.shipment.planned_eta)} />
            <Line label="ETA confidence" value={detail.eta_confidence ?? "—"} />
            <Line label="Contribution band" value={detail.shipment.contribution_band} />
          </CardContent>
        </Card>

        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Confidence and movement gaps</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm text-mutedForeground">
            <div>
              <p className="font-medium text-foreground">Confidence reasons</p>
              <ul className="mt-2 space-y-2">
                {detail.confidence_reasons.map((reason) => (
                  <li key={reason} className="rounded-xl bg-muted px-4 py-3">
                    {reason}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="font-medium text-foreground">Fallback behavior</p>
              <ul className="mt-2 space-y-2">
                {detail.fallback_notes.map((note) => (
                  <li key={note} className="rounded-xl border border-dashed px-4 py-3">
                    {note}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="font-medium text-foreground">Movement gaps</p>
              <ul className="mt-2 space-y-2">
                {detail.movement_gaps.map((note) => (
                  <li key={note} className="rounded-xl border border-dashed px-4 py-3">
                    {note}
                  </li>
                ))}
                {detail.movement_gaps.length === 0 ? (
                  <li className="rounded-xl border border-dashed px-4 py-3">
                    No obvious movement data gaps are currently flagged.
                  </li>
                ) : null}
              </ul>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Latest port summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {detail.port_summary ? (
              <>
                <Line label="Port status" value={detail.port_summary.port_status.replaceAll("_", " ")} />
                <Line label="Berth state" value={detail.port_summary.latest_berth_state.replaceAll("_", " ")} />
                <Line label="Waiting time" value={`${Number(detail.port_summary.waiting_time_days).toFixed(2)} d`} />
                <Line label="Freshness" value={detail.port_summary.freshness.freshness_label} />
                <Line label="Confidence" value={detail.port_summary.confidence} />
              </>
            ) : (
              <p className="text-mutedForeground">No port summary is available yet.</p>
            )}
          </CardContent>
        </Card>

        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Latest inland summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {detail.inland_summary ? (
              <>
                <Line label="Dispatch status" value={detail.inland_summary.dispatch_status.replaceAll("_", " ")} />
                <Line label="Transporter" value={detail.inland_summary.transporter_name ?? "—"} />
                <Line label="Expected arrival" value={formatDate(detail.inland_summary.expected_arrival)} />
                <Line label="Freshness" value={detail.inland_summary.freshness.freshness_label} />
                <Line label="Confidence" value={detail.inland_summary.confidence} />
              </>
            ) : (
              <p className="text-mutedForeground">No inland summary is available yet.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>Movement interpretation notes</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-mutedForeground">
          {detail.movement_notes.map((note) => (
            <div key={note} className="rounded-xl bg-muted px-4 py-3">
              {note}
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className="bg-card/90 shadow-panel">
        <CardHeader>
          <CardTitle>ETA / update history</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {detail.updates.map((update) => (
            <div key={`${update.source}-${update.event_time}`} className="rounded-2xl border bg-card p-4 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold">{update.event_type}</span>
                <span className="text-mutedForeground">{formatDate(update.event_time)}</span>
              </div>
              <p className="mt-2 text-mutedForeground">Source: {update.source}</p>
              {update.notes ? <p className="mt-1 text-mutedForeground">{update.notes}</p> : null}
            </div>
          ))}
          {detail.updates.length === 0 ? (
            <p className="text-sm text-mutedForeground">No shipment update history is available.</p>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Port events</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {detail.port_events.map((event, index) => (
              <div key={`${event.updated_at}-${index}`} className="rounded-2xl border bg-card p-4">
                <p className="font-semibold">{event.berth_status}</p>
                <p className="mt-1 text-mutedForeground">Waiting days: {event.waiting_days}</p>
                <p className="text-mutedForeground">Updated: {formatDate(event.updated_at)}</p>
              </div>
            ))}
            {detail.port_events.length === 0 ? (
              <p className="text-mutedForeground">No port events linked yet.</p>
            ) : null}
          </CardContent>
        </Card>

        <Card className="bg-card/90 shadow-panel">
          <CardHeader>
            <CardTitle>Inland movements</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {detail.inland_movements.map((movement, index) => (
              <div key={`${movement.updated_at}-${index}`} className="rounded-2xl border bg-card p-4">
                <p className="font-semibold">{movement.mode}</p>
                <p className="mt-1 text-mutedForeground">
                  {movement.origin_location ?? "Unknown origin"} to {movement.destination_location ?? "Unknown destination"}
                </p>
                <p className="text-mutedForeground">State: {movement.current_state}</p>
              </div>
            ))}
            {detail.inland_movements.length === 0 ? (
              <p className="text-mutedForeground">No inland movements linked yet.</p>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-muted p-4">
      <p className="text-xs uppercase tracking-[0.18em] text-mutedForeground">{label}</p>
      <p className="mt-2 text-lg font-semibold">{value}</p>
    </div>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-xl bg-muted px-4 py-3">
      <span className="text-mutedForeground">{label}</span>
      <span className="font-semibold">{value}</span>
    </div>
  );
}

function formatDate(value: string | null) {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
