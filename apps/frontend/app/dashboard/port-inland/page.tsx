"use client";

import { Anchor, Link2, Search, Ship, TrainFront, Truck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type {
  ContainerSearchResponse,
  LinkedShipmentStatus,
  ShipmentOption,
  TrackingEvent,
} from "@steelops/contracts";

import { Badge } from "@/components/ui/badge";

const containerPattern = /^[A-Z]{4}\d{7}$/;

export default function PortInlandMonitoringPage() {
  const [containerNo, setContainerNo] = useState("");
  const [carrierCode, setCarrierCode] = useState("");
  const [searchResult, setSearchResult] = useState<ContainerSearchResponse | null>(null);
  const [shipments, setShipments] = useState<ShipmentOption[]>([]);
  const [selectedShipmentId, setSelectedShipmentId] = useState("");
  const [linkedStatus, setLinkedStatus] = useState<LinkedShipmentStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isLinking, setIsLinking] = useState(false);

  const normalizedContainer = useMemo(
    () => containerNo.trim().toUpperCase().replace(/\s+/g, ""),
    [containerNo],
  );
  const isContainerValid = containerPattern.test(normalizedContainer);
  const carrierOptions = searchResult?.carrier_detection.options ?? [];
  const resolvedCarrier =
    carrierCode || searchResult?.carrier_detection.carrier_code || "";
  const sortedEvents = useMemo(
    () =>
      [...(searchResult?.events ?? [])].sort(
        (left, right) =>
          new Date(left.event_datetime).getTime() - new Date(right.event_datetime).getTime()
          || left.event_type.localeCompare(right.event_type)
          || (left.location_code ?? "").localeCompare(right.location_code ?? ""),
      ),
    [searchResult?.events],
  );

  useEffect(() => {
    async function loadShipments() {
      try {
        const response = await fetch("/api/shipments");
        const body = await readJson<ShipmentOption[] | { detail?: string }>(response);
        if (!response.ok) {
          setError(
            body && "detail" in body && typeof body.detail === "string"
              ? body.detail
              : "Shipment list could not be loaded.",
          );
          return;
        }
        setShipments(Array.isArray(body) ? body : []);
      } catch {
        setError("Shipment list could not be loaded.");
      }
    }
    loadShipments();
  }, []);

  async function searchContainer() {
    setLinkedStatus(null);
    setError(null);
    if (!isContainerValid) {
      setError("Container number must be 4 letters followed by 7 digits, for example MSCU1234567.");
      return;
    }
    setIsSearching(true);
    try {
      const response = await fetch("/api/tracking/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          container_no: normalizedContainer,
          carrier_code: carrierCode || undefined,
        }),
      });
      const body = await readJson<ContainerSearchResponse | { detail?: string }>(response);
      if (!response.ok) {
        throw new Error(
          body && "detail" in body && typeof body.detail === "string"
            ? body.detail
            : "Container search failed",
        );
      }
      if (!isContainerSearchResponse(body)) throw new Error("Container search failed");
      const result = body;
      setSearchResult(result);
      if (result.carrier_detection.carrier_code) {
        setCarrierCode(result.carrier_detection.carrier_code);
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Container search failed");
    } finally {
      setIsSearching(false);
    }
  }

  async function linkShipment() {
    setError(null);
    if (!searchResult || !selectedShipmentId || !resolvedCarrier) return;
    setIsLinking(true);
    try {
      const response = await fetch("/api/tracking/link", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          container_no: searchResult.container_no,
          carrier_code: resolvedCarrier,
          shipment_id: Number(selectedShipmentId),
          tracking_source: searchResult.tracking_source,
        }),
      });
      const body = await readJson<LinkedShipmentStatus | { detail?: string }>(response);
      if (!response.ok) {
        throw new Error(
          body && "detail" in body && typeof body.detail === "string"
            ? body.detail
            : "Shipment link failed",
        );
      }
      if (!isLinkedShipmentStatus(body)) throw new Error("Shipment link failed");
      setLinkedStatus(body);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Shipment link failed");
    } finally {
      setIsLinking(false);
    }
  }

  return (
    <div className="grid gap-5">
      <section className="rounded-3xl border bg-card/90 p-6 shadow-panel">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-mutedForeground">
              Port & inland monitoring
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight">
              Container tracking
            </h2>
          </div>
          <div className="grid gap-3 md:grid-cols-[minmax(220px,1fr)_180px_auto]">
            <label className="grid gap-2 text-sm">
              <span className="font-medium">Container number</span>
              <input
                value={containerNo}
                onChange={(event) => setContainerNo(event.target.value.toUpperCase())}
                placeholder="MSCU1234567"
                className="rounded-2xl border bg-card px-4 py-3"
              />
            </label>
            <label className="grid gap-2 text-sm">
              <span className="font-medium">Carrier/source</span>
              <select
                value={carrierCode}
                onChange={(event) => setCarrierCode(event.target.value)}
                className="rounded-2xl border bg-card px-4 py-3"
              >
                <option value="">Auto detect</option>
                {carrierOptions.map((carrier) => (
                  <option key={carrier.code} value={carrier.code}>
                    {carrier.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={searchContainer}
              disabled={isSearching}
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-primaryForeground disabled:opacity-60"
              title="Search container tracking"
            >
              <Search className="h-4 w-4" />
              {isSearching ? "Searching" : "Search"}
            </button>
          </div>
        </div>
        {containerNo && !isContainerValid ? (
          <p className="mt-3 text-sm text-primary">
            Use ISO 6346 format: 4 letters and 7 digits.
          </p>
        ) : null}
        {error ? <p className="mt-3 rounded-2xl bg-muted p-3 text-sm text-primary">{error}</p> : null}
      </section>

      {searchResult ? (
        <section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="rounded-3xl border bg-card/90 p-6 shadow-panel">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-xl font-semibold">{searchResult.container_no}</h3>
                <p className="mt-1 text-sm text-mutedForeground">
                  {searchResult.carrier_detection.carrier_name ??
                    "Carrier needs manual selection"}
                </p>
              </div>
              <Badge variant="outline">{searchResult.carrier_detection.confidence}</Badge>
            </div>
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              <SummaryMetric label="Latest event" value={searchResult.latest_event?.event_type ?? "None"} />
              <SummaryMetric label="Latest ETA" value={formatDate(searchResult.latest_eta)} />
              <SummaryMetric label="Source" value={searchResult.tracking_source} />
            </div>
            {searchResult.carrier_detection.requires_manual_selection ? (
              <p className="mt-4 rounded-2xl bg-muted p-4 text-sm text-mutedForeground">
                Carrier could not be detected from the owner prefix. Select a carrier/source and search again.
              </p>
            ) : null}
            {searchResult.linked_statuses.length > 0 ? (
              <div className="mt-4 rounded-2xl border bg-card p-4 text-sm">
                <p className="font-semibold">Already linked</p>
                <div className="mt-2 grid gap-2">
                  {searchResult.linked_statuses.map((status) => (
                    <p key={`${status.shipment_id}-${status.container_no}`} className="text-mutedForeground">
                      {status.container_no} is linked to {status.shipment_ref}.
                    </p>
                  ))}
                </div>
              </div>
            ) : null}
            <Timeline events={sortedEvents} />
          </div>

          <aside className="rounded-3xl border bg-card/90 p-6 shadow-panel">
            <div className="flex items-center gap-2">
              <Link2 className="h-4 w-4 text-primary" />
              <h3 className="text-lg font-semibold">Link to shipment</h3>
            </div>
            <label className="mt-5 grid gap-2 text-sm">
              <span className="font-medium">Existing shipment</span>
              <select
                value={selectedShipmentId}
                onChange={(event) => setSelectedShipmentId(event.target.value)}
                className="rounded-2xl border bg-card px-4 py-3"
              >
                <option value="">Select shipment</option>
                {shipments.map((shipment) => (
                  <option key={shipment.id} value={shipment.id}>
                    {shipment.shipment_id} - {shipment.plant_name} - {shipment.material_name}
                  </option>
                ))}
              </select>
            </label>
            {shipments.length === 0 ? (
              <p className="mt-3 rounded-2xl bg-muted p-3 text-sm text-mutedForeground">
                No matching shipments are available for this tenant yet.
              </p>
            ) : null}
            {!resolvedCarrier ? (
              <p className="mt-3 rounded-2xl bg-muted p-3 text-sm text-mutedForeground">
                Select a carrier/source before linking this container.
              </p>
            ) : null}
            <button
              type="button"
              onClick={linkShipment}
              disabled={!selectedShipmentId || !resolvedCarrier || isLinking}
              className="mt-4 w-full rounded-2xl bg-primary px-5 py-3 text-sm font-semibold text-primaryForeground disabled:opacity-60"
            >
              {isLinking ? "Linking" : "Link to Shipment"}
            </button>
            {linkedStatus ? <LinkedStatusPanel status={linkedStatus} /> : null}
            {linkedStatus?.already_linked ? (
              <p className="mt-3 rounded-2xl bg-muted p-3 text-sm text-mutedForeground">
                This container was already linked to the selected shipment. Tracking was refreshed without changing the original link time.
              </p>
            ) : null}
          </aside>
        </section>
      ) : null}
    </div>
  );
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border bg-card p-4">
      <p className="text-xs uppercase tracking-[0.16em] text-mutedForeground">{label}</p>
      <p className="mt-2 break-words text-sm font-semibold">{value}</p>
    </div>
  );
}

function Timeline({ events }: { events: TrackingEvent[] }) {
  return (
    <div className="mt-6">
      <h3 className="text-lg font-semibold">Tracking timeline</h3>
      <div className="mt-4 grid gap-3">
        {events.map((event) => (
          <div key={`${event.event_type}-${event.event_datetime}`} className="grid gap-3 rounded-2xl border bg-card p-4 md:grid-cols-[32px_minmax(0,1fr)_130px]">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
              {modeIcon(event.transport_mode)}
            </div>
            <div className="min-w-0">
              <p className="font-semibold">{event.event_type}</p>
              <p className="mt-1 break-words text-sm text-mutedForeground">
                {event.location_name ?? "Unknown location"} {event.location_code ? `(${event.location_code})` : ""}
              </p>
              {event.vessel_name ? (
                <p className="mt-1 text-xs text-mutedForeground">
                  {event.vessel_name} {event.voyage_no ? `· ${event.voyage_no}` : ""}
                </p>
              ) : null}
            </div>
            <p className="text-sm text-mutedForeground md:text-right">{formatDate(event.event_datetime)}</p>
          </div>
        ))}
        {events.length === 0 ? (
          <p className="rounded-2xl bg-muted p-4 text-sm text-mutedForeground">
            Select a carrier/source to pull mock tracking events.
          </p>
        ) : null}
      </div>
    </div>
  );
}

async function readJson<T>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

function isContainerSearchResponse(
  value: ContainerSearchResponse | { detail?: string } | null,
): value is ContainerSearchResponse {
  return Boolean(value && "container_no" in value && "carrier_detection" in value);
}

function isLinkedShipmentStatus(
  value: LinkedShipmentStatus | { detail?: string } | null,
): value is LinkedShipmentStatus {
  return Boolean(value && "shipment_id" in value && "shipment_ref" in value);
}

function LinkedStatusPanel({ status }: { status: LinkedShipmentStatus }) {
  return (
    <div className="mt-5 rounded-2xl border bg-card p-4">
      <p className="text-sm font-semibold">{status.shipment_ref}</p>
      <div className="mt-3 grid gap-3 text-sm">
        <StatusRow label="Current milestone" value={status.current_milestone} />
        <StatusRow label="Current location" value={status.current_location} />
        <StatusRow label="Planned ETA" value={formatDate(status.planned_eta)} />
        <StatusRow label="Latest ETA" value={formatDate(status.latest_eta)} />
        <StatusRow label="Delay days" value={status.delay_days === null ? "Unknown" : String(status.delay_days)} />
        <StatusRow label="Delay status" value={status.delay_status} />
        <StatusRow label="Last updated" value={formatDate(status.last_tracking_update_at)} />
      </div>
    </div>
  );
}

function StatusRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="text-mutedForeground">{label}</span>
      <span className="break-words text-right font-medium">{value ?? "Unknown"}</span>
    </div>
  );
}

function modeIcon(mode: TrackingEvent["transport_mode"]) {
  if (mode === "rail") return <TrainFront className="h-4 w-4" />;
  if (mode === "truck") return <Truck className="h-4 w-4" />;
  if (mode === "ocean") return <Ship className="h-4 w-4" />;
  return <Anchor className="h-4 w-4" />;
}

function formatDate(value: string | null | undefined) {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
