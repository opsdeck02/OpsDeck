from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import InlandMovement, Material, Plant, PortEvent, Shipment, ShipmentUpdate
from app.models.enums import ShipmentState
from app.modules.shipments.confidence import (
    assess_freshness,
    ensure_optional_utc,
    ensure_utc,
    evaluate_confidence,
)
from app.modules.shipments.movement import (
    build_context as build_movement_context,
)
from app.modules.shipments.movement import (
    build_inland_summary,
    build_port_summary,
    movement_gaps,
    movement_notes,
)
from app.modules.shipments.schemas import (
    InlandMovementOut,
    PortEventOut,
    ShipmentDetailResponse,
    ShipmentListItem,
    ShipmentUpdateEvent,
)
from app.schemas.context import RequestContext

VISIBLE_STATES = {
    "planned",
    "on_water",
    "at_port",
    "discharging",
    "in_transit",
    "delivered",
    "cancelled",
}


@dataclass
class ShipmentContext:
    shipment: Shipment
    plant: Plant | None
    material: Material | None
    updates: list[ShipmentUpdate]
    port_events: list[PortEvent]
    inland_movements: list[InlandMovement]


def list_shipments(
    db: Session,
    context: RequestContext,
    *,
    plant_id: int | None = None,
    material_id: int | None = None,
    state: str | None = None,
    search: str | None = None,
) -> list[ShipmentListItem]:
    query = select(Shipment).where(Shipment.tenant_id == context.tenant_id)
    if plant_id is not None:
        query = query.where(Shipment.plant_id == plant_id)
    if material_id is not None:
        query = query.where(Shipment.material_id == material_id)
    if search:
        term = f"%{search.lower()}%"
        query = query.where(
            or_(
                Shipment.shipment_id.ilike(term),
                Shipment.vessel_name.ilike(term),
            )
        )

    shipments = list(db.scalars(query.order_by(Shipment.current_eta)))
    items = [build_shipment_item(db, shipment) for shipment in shipments]
    if state:
        state = state.lower().strip()
        items = [item for item in items if item.shipment_state == state]
    return items


def get_shipment_detail(
    db: Session,
    context: RequestContext,
    shipment_id: str,
) -> ShipmentDetailResponse | None:
    shipment = db.scalar(
        select(Shipment).where(
            Shipment.tenant_id == context.tenant_id,
            Shipment.shipment_id == shipment_id,
        )
    )
    if shipment is None:
        return None

    item = build_shipment_item(db, shipment)
    ctx = load_context(db, shipment)
    movement_ctx = build_movement_context(db, shipment)
    port_summary = build_port_summary(movement_ctx)
    inland_summary = build_inland_summary(movement_ctx)
    gap_notes = movement_gaps(movement_ctx, port_summary, inland_summary)
    return ShipmentDetailResponse(
        shipment=item,
        supplier_name=shipment.supplier_name,
        imo_number=shipment.imo_number,
        mmsi=shipment.mmsi,
        eta_confidence=shipment.eta_confidence,
        source_of_truth=shipment.source_of_truth,
        confidence_reasons=shipment_confidence_reasons(ctx, item),
        fallback_notes=fallback_notes(ctx, item),
        updates=[
            ShipmentUpdateEvent(
                source=update.source,
                event_type=update.event_type,
                event_time=ensure_utc(update.event_time),
                notes=update.notes,
            )
            for update in sorted(
                ctx.updates,
                key=lambda record: ensure_utc(record.event_time),
                reverse=True,
            )
        ],
        port_events=[
            PortEventOut(
                berth_status=event.berth_status,
                waiting_days=event.waiting_days,
                discharge_started_at=ensure_optional_utc(event.discharge_started_at),
                discharge_rate_mt_per_day=event.discharge_rate_mt_per_day,
                estimated_demurrage_exposure=event.estimated_demurrage_exposure,
                updated_at=ensure_utc(event.updated_at),
            )
            for event in sorted(
                ctx.port_events,
                key=lambda record: ensure_utc(record.updated_at),
                reverse=True,
            )
        ],
        inland_movements=[
            InlandMovementOut(
                mode=movement.mode,
                carrier_name=movement.carrier_name,
                origin_location=movement.origin_location,
                destination_location=movement.destination_location,
                planned_departure_at=ensure_optional_utc(movement.planned_departure_at),
                planned_arrival_at=ensure_optional_utc(movement.planned_arrival_at),
                actual_departure_at=ensure_optional_utc(movement.actual_departure_at),
                actual_arrival_at=ensure_optional_utc(movement.actual_arrival_at),
                current_state=movement.current_state,
                updated_at=ensure_utc(movement.updated_at),
            )
            for movement in sorted(
                ctx.inland_movements,
                key=lambda record: ensure_utc(record.updated_at),
                reverse=True,
            )
        ],
        port_summary=port_summary,
        inland_summary=inland_summary,
        movement_gaps=gap_notes,
        movement_notes=movement_notes(port_summary, inland_summary, gap_notes),
    )


def build_shipment_item(db: Session, shipment: Shipment) -> ShipmentListItem:
    ctx = load_context(db, shipment)
    derived_state = derive_state(ctx)
    confidence = derive_confidence(ctx, derived_state)
    sources = contributing_sources(ctx)
    return ShipmentListItem(
        id=shipment.id,
        shipment_id=shipment.shipment_id,
        plant_id=shipment.plant_id,
        plant_name=ctx.plant.name if ctx.plant else f"Plant {shipment.plant_id}",
        material_id=shipment.material_id,
        material_name=ctx.material.name if ctx.material else f"Material {shipment.material_id}",
        supplier_name=shipment.supplier_name,
        quantity_mt=shipment.quantity_mt,
        vessel_name=shipment.vessel_name,
        origin_port=shipment.origin_port,
        destination_port=shipment.destination_port,
        planned_eta=ensure_utc(shipment.planned_eta),
        current_eta=ensure_utc(shipment.current_eta),
        shipment_state=derived_state,
        confidence=confidence,
        latest_status_source=latest_status_source(ctx),
        last_update_at=last_update_at(ctx),
        contributing_data_sources=sources,
        contribution_band=shipment_contribution_band(derived_state),
    )


def load_context(db: Session, shipment: Shipment) -> ShipmentContext:
    return ShipmentContext(
        shipment=shipment,
        plant=db.scalar(select(Plant).where(Plant.id == shipment.plant_id)),
        material=db.scalar(select(Material).where(Material.id == shipment.material_id)),
        updates=list(
            db.scalars(
                select(ShipmentUpdate)
                .where(
                    ShipmentUpdate.tenant_id == shipment.tenant_id,
                    ShipmentUpdate.shipment_id == shipment.id,
                )
                .order_by(ShipmentUpdate.event_time.desc())
            )
        ),
        port_events=list(
            db.scalars(
                select(PortEvent)
                .where(
                    PortEvent.tenant_id == shipment.tenant_id,
                    PortEvent.shipment_id == shipment.id,
                )
                .order_by(PortEvent.updated_at.desc())
            )
        ),
        inland_movements=list(
            db.scalars(
                select(InlandMovement)
                .where(
                    InlandMovement.tenant_id == shipment.tenant_id,
                    InlandMovement.shipment_id == shipment.id,
                )
                .order_by(InlandMovement.updated_at.desc())
            )
        ),
    )


def derive_state(ctx: ShipmentContext) -> str:
    shipment = ctx.shipment
    base_state = shipment.current_state
    latest_port = ctx.port_events[0] if ctx.port_events else None
    latest_inland = ctx.inland_movements[0] if ctx.inland_movements else None

    if base_state == ShipmentState.CANCELLED:
        return "cancelled"
    if base_state == ShipmentState.DELIVERED:
        return "delivered"

    if latest_inland:
        inland_state = latest_inland.current_state.lower().strip().replace(" ", "_")
        if inland_state in {"delivered", "completed", "arrived"} or latest_inland.actual_arrival_at:
            return "delivered"
        if inland_state == "cancelled":
            return "cancelled"
        return "in_transit"

    if latest_port:
        berth_status = latest_port.berth_status.lower().strip().replace(" ", "_")
        if latest_port.discharge_started_at or berth_status in {
            "discharging",
            "discharge_started",
            "unloading",
        }:
            return "discharging"
        if berth_status in {"at_port", "berthed", "waiting", "anchored", "arrived"}:
            return "at_port"

    if base_state == ShipmentState.DISCHARGING:
        return "discharging"
    if base_state == ShipmentState.AT_PORT:
        return "at_port"
    if base_state == ShipmentState.INLAND_TRANSIT:
        return "in_transit"
    if base_state in {ShipmentState.IN_TRANSIT, ShipmentState.DELAYED}:
        if shipment.vessel_name or shipment.imo_number or shipment.mmsi:
            return "on_water"
        return "in_transit"
    return "planned"


def latest_status_source(ctx: ShipmentContext) -> str:
    if ctx.inland_movements:
        return "inland_movement"
    if ctx.port_events:
        return "port_event"
    if ctx.updates:
        return ctx.updates[0].source
    return ctx.shipment.source_of_truth


def last_update_at(ctx: ShipmentContext) -> datetime:
    timestamps = [ensure_utc(ctx.shipment.latest_update_at)]
    timestamps.extend(ensure_utc(record.event_time) for record in ctx.updates)
    timestamps.extend(ensure_utc(record.updated_at) for record in ctx.port_events)
    timestamps.extend(ensure_utc(record.updated_at) for record in ctx.inland_movements)
    return max(timestamps)


def contributing_sources(ctx: ShipmentContext) -> list[str]:
    sources = {ctx.shipment.source_of_truth}
    sources.update(update.source for update in ctx.updates)
    if ctx.port_events:
        sources.add("port_event")
    if ctx.inland_movements:
        sources.add("inland_movement")
    return sorted(source for source in sources if source)


def derive_confidence(ctx: ShipmentContext, derived_state: str) -> str:
    has_eta = ctx.shipment.current_eta is not None
    has_supporting_events = bool(ctx.port_events or ctx.inland_movements or ctx.updates)
    conflict = state_conflict(ctx, derived_state)
    freshness = assess_freshness(last_update_at(ctx))
    level, _ = evaluate_confidence(
        freshness=freshness,
        total_fields=2,
        present_fields=(1 if has_eta else 0) + (1 if has_supporting_events else 0),
        has_conflict=conflict,
        missing_fields=[
            field
            for field, present in (
                ("current ETA", has_eta),
                ("supporting movement signals", has_supporting_events),
            )
            if not present
        ],
    )
    return level


def shipment_confidence_reasons(ctx: ShipmentContext, item: ShipmentListItem) -> list[str]:
    freshness = assess_freshness(item.last_update_at)
    has_eta = ctx.shipment.current_eta is not None
    has_supporting_events = bool(ctx.port_events or ctx.inland_movements or ctx.updates)
    _, reasons = evaluate_confidence(
        freshness=freshness,
        total_fields=2,
        present_fields=(1 if has_eta else 0) + (1 if has_supporting_events else 0),
        has_conflict=state_conflict(ctx, item.shipment_state),
        missing_fields=[
            field
            for field, present in (
                ("current ETA", has_eta),
                ("supporting movement signals", has_supporting_events),
            )
            if not present
        ],
    )
    if not ctx.port_events and not ctx.inland_movements and not ctx.updates:
        reasons.append("Only shipment master data is available.")
    return reasons


def fallback_notes(ctx: ShipmentContext, item: ShipmentListItem) -> list[str]:
    notes: list[str] = []
    if item.shipment_state == "on_water":
        notes.append("On-water is inferred from shipment state plus vessel markers.")
    if item.shipment_state == "in_transit" and not ctx.inland_movements:
        notes.append(
            "In-transit falls back to shipment master state because inland data is absent."
        )
    if not ctx.port_events:
        notes.append("No port events available for port-state refinement.")
    if not ctx.inland_movements:
        notes.append("No inland movements available for post-discharge refinement.")
    return notes


def state_conflict(ctx: ShipmentContext, derived_state: str) -> bool:
    base = ctx.shipment.current_state.value
    has_vessel_markers = bool(
        ctx.shipment.vessel_name or ctx.shipment.imo_number or ctx.shipment.mmsi
    )
    if base == "inland_transit":
        base = "in_transit"
    if base == "in_transit" and has_vessel_markers:
        base = "on_water"
    if base == "delayed" and has_vessel_markers:
        base = "on_water"
    return base != derived_state and bool(ctx.port_events or ctx.inland_movements)


def shipment_contribution_band(derived_state: str) -> str:
    if derived_state == "on_water":
        return "low"
    if derived_state in {"at_port", "discharging"}:
        return "medium"
    if derived_state == "in_transit":
        return "high"
    return "excluded"
