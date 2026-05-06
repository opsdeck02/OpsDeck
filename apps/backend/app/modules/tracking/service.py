from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Container, Material, Plant, Shipment, ShipmentContainer, TrackingEvent
from app.modules.tracking.providers import get_tracking_provider
from app.modules.tracking.schemas import (
    CarrierDetection,
    CarrierOption,
    ContainerSearchResponse,
    LinkedShipmentStatus,
    ShipmentOption,
    TrackingEventOut,
)
from app.schemas.context import RequestContext

CONTAINER_PATTERN = re.compile(r"^[A-Z]{4}\d{7}$")

CARRIER_PREFIXES = {
    "MSCU": ("MSC", "Mediterranean Shipping Company"),
    "MAEU": ("MAEU", "Maersk"),
    "CMAU": ("CMA", "CMA CGM"),
    "HLCU": ("HLC", "Hapag-Lloyd"),
    "OOLU": ("OOL", "OOCL"),
    "ONEU": ("ONE", "Ocean Network Express"),
    "COSU": ("COSCO", "COSCO Shipping"),
    "EMCU": ("EMC", "Evergreen"),
    "TCLU": ("TCL", "Triton / leasing source"),
}

DEFAULT_CARRIERS = [
    CarrierOption(code="MSC", name="Mediterranean Shipping Company"),
    CarrierOption(code="MAEU", name="Maersk"),
    CarrierOption(code="CMA", name="CMA CGM"),
    CarrierOption(code="HLC", name="Hapag-Lloyd"),
    CarrierOption(code="ONE", name="Ocean Network Express"),
    CarrierOption(code="COSCO", name="COSCO Shipping"),
    CarrierOption(code="MOCK", name="Mock tracking provider"),
]

ETA_EVENT_TYPES = {
    "Vessel arrival",
    "Discharged",
    "Available for pickup",
    "Rail arrival",
    "Truck appointment",
    "Delivered",
}


def normalize_container_no(container_no: str) -> str:
    value = container_no.strip().upper().replace(" ", "")
    if not CONTAINER_PATTERN.fullmatch(value):
        raise ValueError("Container number must be 4 letters followed by 7 digits")
    return value


def detect_carrier(container_no: str) -> CarrierDetection:
    normalized = normalize_container_no(container_no)
    owner_prefix = normalized[:4]
    carrier = CARRIER_PREFIXES.get(owner_prefix)
    if carrier:
        return CarrierDetection(
            owner_prefix=owner_prefix,
            carrier_code=carrier[0],
            carrier_name=carrier[1],
            confidence="high",
            requires_manual_selection=False,
            options=DEFAULT_CARRIERS,
        )
    return CarrierDetection(
        owner_prefix=owner_prefix,
        carrier_code=None,
        carrier_name=None,
        confidence="unknown",
        requires_manual_selection=True,
        options=DEFAULT_CARRIERS,
    )


def calculate_delay_status(
    planned_eta: datetime | None,
    latest_eta: datetime | None,
) -> tuple[int | None, str]:
    if planned_eta is None or latest_eta is None:
        return None, "unknown"
    delay_days = (latest_eta.date() - planned_eta.date()).days
    if delay_days > 0:
        return delay_days, "delayed"
    if delay_days < 0:
        return delay_days, "early"
    return delay_days, "on_time"


def search_container(
    container_no: str,
    carrier_code: str | None = None,
    tracking_source: str = "mock",
    db: Session | None = None,
    context: RequestContext | None = None,
) -> ContainerSearchResponse:
    normalized = normalize_container_no(container_no)
    detection = detect_carrier(normalized)
    resolved_carrier = (carrier_code or detection.carrier_code or "").strip().upper()
    if not resolved_carrier:
        return ContainerSearchResponse(
            container_no=normalized,
            carrier_detection=detection,
            tracking_source=tracking_source,
            events=[],
            latest_event=None,
            latest_eta=None,
            linked_statuses=linked_statuses_for_container(db, context, normalized),
        )

    provider = get_tracking_provider(tracking_source)
    provider.search_container(normalized, resolved_carrier)
    events = provider.get_tracking_events(normalized, resolved_carrier)
    events = sort_events(events)
    if db is not None and context is not None:
        upsert_container_selection(
            db,
            context,
            container_no=normalized,
            carrier_code=resolved_carrier,
            tracking_source=tracking_source,
            detection_confidence=detection.confidence if detection.carrier_code else "manual",
        )
    return ContainerSearchResponse(
        container_no=normalized,
        carrier_detection=detection.model_copy(
            update={
                "carrier_code": resolved_carrier,
                "carrier_name": carrier_name(resolved_carrier) or detection.carrier_name,
                "confidence": detection.confidence if detection.carrier_code else "manual",
                "requires_manual_selection": False,
            }
        ),
        tracking_source=tracking_source,
        events=events,
        latest_event=latest_event(events),
        latest_eta=derive_latest_eta(events),
        linked_statuses=linked_statuses_for_container(db, context, normalized),
    )


def carrier_name(carrier_code: str) -> str | None:
    normalized = carrier_code.upper()
    return next((carrier.name for carrier in DEFAULT_CARRIERS if carrier.code == normalized), None)


def list_shipment_options(db: Session, context: RequestContext) -> list[ShipmentOption]:
    shipments = list(
        db.scalars(
            select(Shipment)
            .where(Shipment.tenant_id == context.tenant_id)
            .order_by(Shipment.current_eta)
        )
    )
    return [
        ShipmentOption(
            id=shipment.id,
            shipment_id=shipment.shipment_id,
            plant_name=db.scalar(select(Plant.name).where(Plant.id == shipment.plant_id))
            or f"Plant {shipment.plant_id}",
            material_name=(
                db.scalar(select(Material.name).where(Material.id == shipment.material_id))
                or f"Material {shipment.material_id}"
            ),
            planned_eta=shipment.planned_eta,
            current_eta=shipment.current_eta,
        )
        for shipment in shipments
    ]


def link_container_to_shipment(
    db: Session,
    context: RequestContext,
    *,
    container_no: str,
    carrier_code: str,
    shipment_id: int,
    tracking_source: str = "mock",
) -> LinkedShipmentStatus:
    normalized = normalize_container_no(container_no)
    carrier_code = carrier_code.strip().upper()
    if not carrier_code:
        raise ValueError("Carrier/source is required")
    shipment = db.scalar(
        select(Shipment).where(Shipment.tenant_id == context.tenant_id, Shipment.id == shipment_id)
    )
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

    container = db.scalar(
        select(Container).where(
            Container.tenant_id == context.tenant_id,
            Container.container_no == normalized,
        )
    )
    detection = detect_carrier(normalized)
    if container is None:
        container = Container(
            tenant_id=context.tenant_id,
            container_no=normalized,
            carrier_code=carrier_code,
            tracking_source=tracking_source,
            detection_confidence=detection.confidence if detection.carrier_code else "manual",
        )
        db.add(container)
        db.flush()
    else:
        container.carrier_code = carrier_code
        container.tracking_source = tracking_source
        container.detection_confidence = (
            detection.confidence if detection.carrier_code else "manual"
        )

    linked_at = datetime.now(UTC)
    already_linked = False
    link = db.scalar(
        select(ShipmentContainer).where(
            ShipmentContainer.tenant_id == context.tenant_id,
            ShipmentContainer.shipment_id == shipment.id,
            ShipmentContainer.container_id == container.id,
        )
    )
    if link is None:
        link = ShipmentContainer(
            tenant_id=context.tenant_id,
            shipment_id=shipment.id,
            container_id=container.id,
            carrier_code=carrier_code,
            tracking_source=tracking_source,
            linked_at=linked_at,
        )
        db.add(link)
    else:
        already_linked = True
        link.carrier_code = carrier_code
        link.tracking_source = tracking_source

    search_result = search_container(normalized, carrier_code, tracking_source, db, context)
    persist_tracking_events(
        db,
        context,
        container_id=container.id,
        shipment_id=shipment.id,
        events=search_result.events,
    )
    update_shipment_from_events(shipment, search_result.events)
    db.commit()
    db.refresh(shipment)
    db.refresh(link)
    return build_linked_status(
        shipment,
        normalized,
        carrier_code,
        tracking_source,
        link.linked_at,
        already_linked=already_linked,
    )


def upsert_container_selection(
    db: Session,
    context: RequestContext,
    *,
    container_no: str,
    carrier_code: str,
    tracking_source: str,
    detection_confidence: str,
) -> Container:
    container = db.scalar(
        select(Container).where(
            Container.tenant_id == context.tenant_id,
            Container.container_no == container_no,
        )
    )
    if container is None:
        container = Container(
            tenant_id=context.tenant_id,
            container_no=container_no,
            carrier_code=carrier_code,
            tracking_source=tracking_source,
            detection_confidence=detection_confidence,
        )
        db.add(container)
    else:
        container.carrier_code = carrier_code
        container.tracking_source = tracking_source
        container.detection_confidence = detection_confidence
    db.flush()
    return container


def persist_tracking_events(
    db: Session,
    context: RequestContext,
    *,
    container_id: int,
    shipment_id: int,
    events: list[TrackingEventOut],
) -> None:
    existing = {
        tracking_event_key(item): item
        for item in db.scalars(
            select(TrackingEvent).where(
                TrackingEvent.tenant_id == context.tenant_id,
                TrackingEvent.container_id == container_id,
                TrackingEvent.shipment_id == shipment_id,
            )
        )
    }
    seen_keys: set[tuple] = set()
    for event in sort_events(events):
        key = tracking_event_out_key(event)
        seen_keys.add(key)
        row = existing.get(key)
        if row is None:
            row = TrackingEvent(
                tenant_id=context.tenant_id,
                container_id=container_id,
                shipment_id=shipment_id,
                event_type=event.event_type,
                event_datetime=event.event_datetime,
                source=event.source,
            )
            db.add(row)
        row.location_name = event.location_name
        row.location_code = event.location_code
        row.transport_mode = event.transport_mode
        row.vessel_name = event.vessel_name
        row.voyage_no = event.voyage_no
        row.raw_payload = json.dumps(event.raw_payload, sort_keys=True)
    stale_ids = [row.id for key, row in existing.items() if key not in seen_keys]
    if stale_ids:
        db.execute(delete(TrackingEvent).where(TrackingEvent.id.in_(stale_ids)))


def tracking_event_key(event: TrackingEvent) -> tuple:
    return (
        event.event_type,
        event.event_datetime,
        event.location_code,
        event.source,
    )


def tracking_event_out_key(event: TrackingEventOut) -> tuple:
    return (
        event.event_type,
        event.event_datetime,
        event.location_code,
        event.source,
    )


def update_shipment_from_events(shipment: Shipment, events: list[TrackingEventOut]) -> None:
    current = latest_event(events)
    latest_eta = derive_latest_eta(events)
    delay_days, delay_status = calculate_delay_status(shipment.planned_eta, latest_eta)
    shipment.latest_eta = latest_eta
    if latest_eta is not None:
        shipment.current_eta = latest_eta
    shipment.delay_days = delay_days
    shipment.delay_status = delay_status
    shipment.current_milestone = current.event_type if current else None
    shipment.current_location = current.location_name if current else None
    shipment.last_tracking_update_at = current.event_datetime if current else None
    if current is not None:
        shipment.latest_update_at = current.event_datetime
        shipment.source_of_truth = current.source


def derive_latest_eta(events: list[TrackingEventOut]) -> datetime | None:
    eta_events = [event for event in events if event.event_type in ETA_EVENT_TYPES]
    if not eta_events:
        return None
    return max(eta_events, key=lambda event: event_sort_key(event)).event_datetime


def latest_event(events: list[TrackingEventOut]) -> TrackingEventOut | None:
    if not events:
        return None
    return max(events, key=lambda event: event_sort_key(event))


def sort_events(events: list[TrackingEventOut]) -> list[TrackingEventOut]:
    return sorted(events, key=event_sort_key)


def event_sort_key(event: TrackingEventOut) -> tuple:
    sequence = event.raw_payload.get("sequence")
    return (
        event.event_datetime,
        int(sequence) if isinstance(sequence, int) else 0,
        event.event_type,
        event.location_code or "",
        event.source,
    )


def linked_statuses_for_container(
    db: Session | None,
    context: RequestContext | None,
    container_no: str,
) -> list[LinkedShipmentStatus]:
    if db is None or context is None:
        return []
    container = db.scalar(
        select(Container).where(
            Container.tenant_id == context.tenant_id,
            Container.container_no == container_no,
        )
    )
    if container is None:
        return []
    links = list(
        db.scalars(
            select(ShipmentContainer)
            .where(
                ShipmentContainer.tenant_id == context.tenant_id,
                ShipmentContainer.container_id == container.id,
            )
            .order_by(ShipmentContainer.linked_at.asc(), ShipmentContainer.id.asc())
        )
    )
    statuses: list[LinkedShipmentStatus] = []
    for link in links:
        shipment = db.get(Shipment, link.shipment_id)
        if shipment is None or shipment.tenant_id != context.tenant_id:
            continue
        statuses.append(
            build_linked_status(
                shipment,
                container_no,
                link.carrier_code,
                link.tracking_source,
                link.linked_at,
                already_linked=True,
            )
        )
    return statuses


def build_linked_status(
    shipment: Shipment,
    container_no: str,
    carrier_code: str,
    tracking_source: str,
    linked_at: datetime,
    already_linked: bool = False,
) -> LinkedShipmentStatus:
    return LinkedShipmentStatus(
        shipment_id=shipment.id,
        shipment_ref=shipment.shipment_id,
        container_no=container_no,
        carrier_code=carrier_code,
        tracking_source=tracking_source,
        planned_eta=shipment.planned_eta,
        latest_eta=shipment.latest_eta,
        delay_days=shipment.delay_days,
        delay_status=shipment.delay_status,
        current_milestone=shipment.current_milestone,
        current_location=shipment.current_location,
        last_tracking_update_at=shipment.last_tracking_update_at,
        linked_at=linked_at,
        already_linked=already_linked,
    )
