"use client";

import { Anchor, Link2, Search, Ship, TrainFront, Truck } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

import type {
  ContainerSearchResponse,
  LinkedShipmentStatus,
  ShipmentOption,
  TrackingEvent,
  VesselPosition,
} from "@steelops/contracts";

import { Badge } from "@/components/ui/badge";

const containerPattern = /^[A-Z]{4}\d{7}$/;
const VesselMap = dynamic(() => import("./vessel-map"), {
  ssr: false,
  loading: () => (
    <div className="mt-4 flex h-[280px] items-center justify-center rounded-2xl border bg-muted text-sm text-mutedForeground">
      Loading map...
    </div>
  ),
});

export default function PortInlandMonitoringPage() {
  const [containerNo, setContainerNo] = useState("");
  const [carrierCode, setCarrierCode] = useState("");
  const [trackingSource, setTrackingSource] = useState("mock");
  const [searchResult, setSearchResult] = useState<ContainerSearchResponse | null>(null);
  const [shipments, setShipments] = useState<ShipmentOption[]>([]);
  const [selectedShipmentId, setSelectedShipmentId] = useState("");
  const [linkedStatus, setLinkedStatus] = useState<LinkedShipmentStatus | null>(null);
  const [vesselPosition, setVesselPosition] = useState<VesselPosition | null>(null);
  const [vesselError, setVesselError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isLinking, setIsLinking] = useState(false);
  const [isVesselLoading, setIsVesselLoading] = useState(false);

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
  const vesselName = useMemo(
    () => [...sortedEvents].reverse().find((event) => event.vessel_name)?.vessel_name ?? null,
    [sortedEvents],
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
              : "Inbound dependency list could not be loaded.",
          );
          return;
        }
        setShipments(Array.isArray(body) ? body : []);
      } catch {
        setError("Inbound dependency list could not be loaded.");
      }
    }
    loadShipments();
  }, []);

  useEffect(() => {
    setSearchResult(null);
    setLinkedStatus(null);
    setVesselPosition(null);
    setVesselError(null);
    setSelectedShipmentId("");
    setError(null);
  }, [trackingSource]);

  useEffect(() => {
    let isActive = true;
    async function loadVesselPosition() {
      setVesselPosition(null);
      setVesselError(null);
      if (!vesselName) {
        setIsVesselLoading(false);
        return;
      }
      setIsVesselLoading(true);
      try {
        const params = new URLSearchParams({ vessel_name: vesselName });
        const response = await fetch(`/api/tracking/vessel-position?${params}`);
        const body = await readJson<VesselPosition | { detail?: string }>(response);
        if (!response.ok) {
          throw new Error(errorMessageFromBody(body, "Vessel position could not be loaded"));
        }
        if (isActive) {
          setVesselPosition(isVesselPosition(body) ? body : null);
        }
      } catch (exc) {
        if (isActive) {
          setVesselError(
            exc instanceof Error ? exc.message : "Vessel position could not be loaded",
          );
        }
      } finally {
        if (isActive) {
          setIsVesselLoading(false);
        }
      }
    }
    loadVesselPosition();
    return () => {
      isActive = false;
    };
  }, [vesselName]);

  async function searchContainer() {
    setSearchResult(null);
    setLinkedStatus(null);
    setVesselPosition(null);
    setVesselError(null);
    setSelectedShipmentId("");
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
          tracking_source: trackingSource,
        }),
      });
      const body = await readJson<ContainerSearchResponse | { detail?: string }>(response);
      if (!response.ok) {
        throw new Error(errorMessageFromBody(body, "Container search failed"));
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
        throw new Error(errorMessageFromBody(body, "Continuity link failed"));
      }
      if (!isLinkedShipmentStatus(body)) throw new Error("Continuity link failed");
      setLinkedStatus(body);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Continuity link failed");
    } finally {
      setIsLinking(false);
    }
  }

  return (
    <div className="grid gap-4">
      <section className="rounded-2xl border bg-card/90 p-4 shadow-panel">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-mutedForeground">
              Continuity visibility source
            </p>
            <h2 className="mt-1 text-xl font-semibold tracking-tight">
              Inbound signal lookup
            </h2>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(220px,1fr)_170px_140px_auto]">
            <label className="grid gap-2 text-sm">
              <span className="font-medium">Container number</span>
              <input
                value={containerNo}
                onChange={(event) => setContainerNo(event.target.value.toUpperCase())}
                placeholder="MSCU1234567"
                className="rounded-xl border bg-card px-3 py-2.5"
              />
            </label>
            <label className="grid gap-2 text-sm">
              <span className="font-medium">Carrier/source</span>
              <select
                value={carrierCode}
                onChange={(event) => setCarrierCode(event.target.value)}
                className="rounded-xl border bg-card px-3 py-2.5"
              >
                <option value="">Auto detect</option>
                {carrierOptions.map((carrier) => (
                  <option key={carrier.code} value={carrier.code}>
                    {carrier.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-2 text-sm">
              <span className="font-medium">Signal source</span>
              <select
                value={trackingSource}
                onChange={(event) => setTrackingSource(event.target.value)}
                className="rounded-xl border bg-card px-3 py-2.5"
              >
                <option value="mock">Mock</option>
                <option value="dcsa">DCSA</option>
              </select>
            </label>
            <button
              type="button"
              onClick={searchContainer}
              disabled={isSearching}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primaryForeground disabled:opacity-60"
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
        {error ? <p className="mt-3 rounded-xl bg-muted p-3 text-sm text-primary">{error}</p> : null}
      </section>

      {searchResult ? (
        <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="rounded-2xl border bg-card/90 p-4 shadow-panel">
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
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <SummaryMetric label="Latest event" value={searchResult.latest_event?.event_type ?? "None"} />
              <SummaryMetric label="Latest ETA" value={formatDate(searchResult.latest_eta)} />
              <SummaryMetric label="Source" value={searchResult.tracking_source} />
            </div>
            {searchResult.carrier_detection.requires_manual_selection ? (
              <p className="mt-4 rounded-xl bg-muted p-3 text-sm text-mutedForeground">
                Carrier could not be detected from the owner prefix. Select a signal source and search again.
              </p>
            ) : null}
            {searchResult.linked_statuses.length > 0 ? (
              <div className="mt-4 rounded-xl border bg-card p-3 text-sm">
                <p className="font-semibold">Already linked to continuity context</p>
                <div className="mt-2 grid gap-2">
                  {searchResult.linked_statuses.map((status) => (
                    <p key={`${status.shipment_id}-${status.container_no}`} className="text-mutedForeground">
                      {status.container_no} supports {status.shipment_ref}.
                    </p>
                  ))}
                </div>
              </div>
            ) : null}
            <Timeline events={sortedEvents} />
            <VesselTrackingCard
              vesselName={vesselName}
              position={vesselPosition}
              isLoading={isVesselLoading}
              error={vesselError}
            />
          </div>

          <aside className="rounded-2xl border bg-card/90 p-4 shadow-panel">
            <div className="flex items-center gap-2">
              <Link2 className="h-4 w-4 text-primary" />
              <h3 className="text-lg font-semibold">Link to inbound dependency</h3>
            </div>
            <label className="mt-4 grid gap-2 text-sm">
              <span className="font-medium">Existing inbound dependency</span>
              <select
                value={selectedShipmentId}
                onChange={(event) => setSelectedShipmentId(event.target.value)}
                className="rounded-xl border bg-card px-3 py-2.5"
              >
                <option value="">Select inbound dependency</option>
                {shipments.map((shipment) => (
                  <option key={shipment.id} value={shipment.id}>
                    {shipment.shipment_id} - {shipment.plant_name} - {shipment.material_name}
                  </option>
                ))}
              </select>
            </label>
            {shipments.length === 0 ? (
              <p className="mt-3 rounded-xl bg-muted p-3 text-sm text-mutedForeground">
                No matching inbound dependencies are available for this tenant yet.
              </p>
            ) : null}
            {!resolvedCarrier ? (
              <p className="mt-3 rounded-xl bg-muted p-3 text-sm text-mutedForeground">
                Select a signal source before linking this container.
              </p>
            ) : null}
            <button
              type="button"
              onClick={linkShipment}
              disabled={!selectedShipmentId || !resolvedCarrier || isLinking}
              className="mt-4 w-full rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primaryForeground disabled:opacity-60"
            >
              {isLinking ? "Linking" : "Link to continuity context"}
            </button>
            {linkedStatus ? <LinkedStatusPanel status={linkedStatus} /> : null}
            {linkedStatus?.already_linked ? (
              <p className="mt-3 rounded-xl bg-muted p-3 text-sm text-mutedForeground">
                This container was already linked to the selected continuity context. Signals were refreshed without changing the original link time.
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
    <div className="rounded-xl border bg-card p-3">
      <p className="text-xs uppercase tracking-[0.16em] text-mutedForeground">{label}</p>
      <p className="mt-2 break-words text-sm font-semibold">{value}</p>
    </div>
  );
}

function Timeline({ events }: { events: TrackingEvent[] }) {
  return (
    <div className="mt-5">
      <h3 className="text-lg font-semibold">Signal chain</h3>
      <div className="mt-3 grid gap-3">
        {events.map((event) => (
          <div key={`${event.event_type}-${event.event_datetime}`} className="grid gap-3 rounded-xl border bg-card p-3 md:grid-cols-[32px_minmax(0,1fr)_130px]">
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
          <p className="rounded-xl bg-muted p-3 text-sm text-mutedForeground">
            No continuity signal events found for this container and source yet.
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

function isVesselPosition(
  value: VesselPosition | { detail?: string } | null,
): value is VesselPosition {
  return Boolean(value && "vessel_name" in value && "lat" in value && "lon" in value);
}

function errorMessageFromBody(value: unknown, fallback: string) {
  if (!value || typeof value !== "object" || !("detail" in value)) return fallback;
  const detail = (value as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return fallback;
}

function LinkedStatusPanel({ status }: { status: LinkedShipmentStatus }) {
  return (
    <div className="mt-5 rounded-xl border bg-card p-3">
      <p className="text-sm font-semibold">{status.shipment_ref}</p>
      <div className="mt-3 grid gap-3 text-sm">
        <StatusRow label="Current milestone" value={status.current_milestone} />
        <StatusRow label="Current location" value={status.current_location} />
        <StatusRow label="Planned ETA" value={formatDate(status.planned_eta)} />
        <StatusRow label="Latest ETA" value={formatDate(status.latest_eta)} />
        <StatusRow label="Delay days" value={status.delay_days === null ? "Unknown" : String(status.delay_days)} />
        <StatusRow label="Delay status" value={status.delay_status} />
        <StatusRow label="Last signal update" value={formatDate(status.last_tracking_update_at)} />
      </div>
    </div>
  );
}

function VesselTrackingCard({
  vesselName,
  position,
  isLoading,
  error,
}: {
  vesselName: string | null;
  position: VesselPosition | null;
  isLoading: boolean;
  error: string | null;
}) {
  return (
    <div className="mt-5 rounded-xl border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-semibold">Vessel visibility signal</h3>
        <Badge variant="outline">Mock AIS</Badge>
      </div>
      {!vesselName ? (
        <p className="mt-3 text-sm text-mutedForeground">
          No vessel name is available from the latest vessel event.
        </p>
      ) : null}
      {isLoading ? (
        <p className="mt-3 text-sm text-mutedForeground">Loading vessel position...</p>
      ) : null}
      {error ? <p className="mt-3 text-sm text-primary">{error}</p> : null}
      {vesselName && !isLoading && !error && !position ? (
        <p className="mt-3 text-sm text-mutedForeground">
          No vessel position data is available for this source.
        </p>
      ) : null}
      {position ? (
        <>
          {position.is_mock ? (
            <p className="mt-3 rounded-xl bg-muted p-3 text-sm text-mutedForeground">
              Scenario vessel position, not live AIS.
            </p>
          ) : null}
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <StatusRow label="Vessel" value={position.vessel_name} />
            <StatusRow label="Position" value={`${position.lat.toFixed(4)}, ${position.lon.toFixed(4)}`} />
            <StatusRow label="Speed" value={`${position.speed_knots.toFixed(1)} kn`} />
            <StatusRow label="Heading" value={`${position.heading_degrees.toFixed(0)} deg`} />
            <StatusRow label="Last update" value={formatDate(position.timestamp)} />
            <StatusRow label="Source" value={position.is_mock ? "Mock AIS" : position.source} />
          </div>
          <VesselMap
            vesselName={position.vessel_name}
            latitude={position.lat}
            longitude={position.lon}
            speedKnots={position.speed_knots}
            headingDegrees={position.heading_degrees}
            timestamp={position.timestamp}
            source={position.source}
            isMock={position.is_mock}
          />
        </>
      ) : null}
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
