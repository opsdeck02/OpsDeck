from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import InlandMovement, Material, Plant, PortEvent, Shipment
from app.modules.shipments.confidence import (
    FreshnessAssessment,
    assess_freshness,
    ensure_optional_utc,
    evaluate_confidence,
)
from app.modules.shipments.schemas import (
    FreshnessInfo,
    InlandMonitoringItem,
    MovementDetailResponse,
    PortMonitoringItem,
    ShipmentListItem,
)
from app.schemas.context import RequestContext

WAITING_STATUSES = {"waiting", "anchored", "queued"}
AT_PORT_STATUSES = {"at_port", "berthed", "arrived", "waiting", "anchored"}
DISCHARGING_STATUSES = {"discharging", "discharge_started", "unloading"}
INLAND_ACTIVE_STATES = {"en_route", "dispatched", "in_transit", "rail", "trucked"}
INLAND_COMPLETE_STATES = {"delivered", "completed", "arrived"}


@dataclass(frozen=True)
class ShipmentMovementContext:
    shipment: Shipment
    plant_name: str
    material_name: str
    port_events: list[PortEvent]
    inland_movements: list[InlandMovement]


def list_port_monitoring(
    db: Session,
    context: RequestContext,
    *,
    plant_id: int | None = None,
    material_id: int | None = None,
    shipment_id: str | None = None,
    confidence: str | None = None,
    delayed_only: bool | None = None,
) -> list[PortMonitoringItem]:
    summaries: list[PortMonitoringItem] = []
    for movement_ctx in shipment_contexts(
        db,
        context.tenant_id,
        plant_id=plant_id,
        material_id=material_id,
        shipment_id=shipment_id,
    ):
        summary = build_port_summary(movement_ctx)
        if summary is None:
            continue
        if confidence and summary.confidence != confidence:
            continue
        if delayed_only is True and not summary.likely_port_delay:
            continue
        summaries.append(summary)
    return summaries


def list_inland_monitoring(
    db: Session,
    context: RequestContext,
    *,
    plant_id: int | None = None,
    material_id: int | None = None,
    shipment_id: str | None = None,
    confidence: str | None = None,
    delayed_only: bool | None = None,
) -> list[InlandMonitoringItem]:
    summaries: list[InlandMonitoringItem] = []
    for movement_ctx in shipment_contexts(
        db,
        context.tenant_id,
        plant_id=plant_id,
        material_id=material_id,
        shipment_id=shipment_id,
    ):
        summary = build_inland_summary(movement_ctx)
        if summary is None:
            continue
        if confidence and summary.confidence != confidence:
            continue
        if delayed_only is True and not summary.inland_delay_flag:
            continue
        summaries.append(summary)
    return summaries


def get_movement_detail(
    db: Session,
    context: RequestContext,
    shipment_id: str,
    shipment_item: ShipmentListItem,
) -> MovementDetailResponse | None:
    movement_ctx = movement_context_by_shipment_id(db, context.tenant_id, shipment_id)
    if movement_ctx is None:
        return None

    port_summary = build_port_summary(movement_ctx)
    inland_summary = build_inland_summary(movement_ctx)
    missing_signals = movement_gaps(movement_ctx, port_summary, inland_summary)
    progress_notes = movement_notes(port_summary, inland_summary, missing_signals)
    overall_freshness = combined_freshness(port_summary, inland_summary)
    overall_confidence = combined_confidence(port_summary, inland_summary)

    return MovementDetailResponse(
        shipment=shipment_item,
        port_summary=port_summary,
        inland_summary=inland_summary,
        overall_confidence=overall_confidence,
        overall_freshness=freshness_info(overall_freshness),
        missing_signals=missing_signals,
        progress_notes=progress_notes,
    )


def build_port_summary(movement_ctx: ShipmentMovementContext) -> PortMonitoringItem | None:
    if not movement_ctx.port_events:
        return None

    shipment = movement_ctx.shipment
    latest_event = movement_ctx.port_events[0]
    berth_state = normalize_state(latest_event.berth_status)
    if latest_event.discharge_started_at or berth_state in DISCHARGING_STATUSES:
        port_status = "discharging"
    elif berth_state in WAITING_STATUSES:
        port_status = "waiting"
    elif berth_state in AT_PORT_STATUSES:
        port_status = "arrived_at_port"
    else:
        port_status = berth_state

    waiting_days = latest_event.waiting_days
    freshness = assess_freshness(latest_event.updated_at)
    likely_port_delay = (
        port_status == "waiting" and waiting_days >= Decimal("2")
    ) or (port_status != "discharging" and freshness.freshness_label == "stale")
    stale_record = freshness.freshness_label == "stale"
    missing_supporting_signal = port_status == "discharging" and (
        latest_event.discharge_started_at is None
        or latest_event.discharge_rate_mt_per_day is None
    )
    missing_fields: list[str] = []
    if not latest_event.berth_status:
        missing_fields.append("berth status")
    if port_status == "discharging" and latest_event.discharge_started_at is None:
        missing_fields.append("discharge started at")
    if port_status == "discharging" and latest_event.discharge_rate_mt_per_day is None:
        missing_fields.append("discharge rate")
    confidence, reasons = evaluate_confidence(
        freshness=freshness,
        total_fields=3,
        present_fields=3 - len(missing_fields),
        has_conflict=False,
        missing_fields=missing_fields,
    )
    if likely_port_delay:
        reasons.append("Port delay heuristic is active.")
    if stale_record:
        reasons.append("Port event stream needs a refresh.")

    return PortMonitoringItem(
        shipment_id=shipment.shipment_id,
        plant_id=shipment.plant_id,
        plant_name=movement_ctx.plant_name,
        material_id=shipment.material_id,
        material_name=movement_ctx.material_name,
        port_status=port_status,
        latest_berth_state=berth_state,
        waiting_time_days=waiting_days,
        latest_discharge_timestamp=ensure_optional_utc(latest_event.discharge_started_at),
        likely_port_delay=likely_port_delay,
        stale_record=stale_record,
        missing_supporting_signal=missing_supporting_signal,
        freshness=freshness_info(freshness),
        confidence=confidence,
        confidence_reasons=reasons,
    )


def build_inland_summary(movement_ctx: ShipmentMovementContext) -> InlandMonitoringItem | None:
    if not movement_ctx.inland_movements:
        return None

    shipment = movement_ctx.shipment
    latest = movement_ctx.inland_movements[0]
    inland_state = normalize_state(latest.current_state)
    if latest.actual_arrival_at or inland_state in INLAND_COMPLETE_STATES:
        dispatch_status = "delivered"
    elif latest.actual_departure_at or inland_state in INLAND_ACTIVE_STATES:
        dispatch_status = "inland_dispatched"
    elif latest.planned_departure_at:
        dispatch_status = "planned_dispatch"
    else:
        dispatch_status = "movement_recorded"

    expected_arrival = ensure_optional_utc(latest.planned_arrival_at)
    actual_arrival = ensure_optional_utc(latest.actual_arrival_at)
    freshness = assess_freshness(latest.updated_at)
    inland_delay_flag = inland_delay_flag_for(latest)
    stale_record = freshness.freshness_label == "stale"
    missing_supporting_signal = (
        dispatch_status != "delivered" and expected_arrival is None
    ) or (dispatch_status == "delivered" and actual_arrival is None)

    missing_fields: list[str] = []
    if latest.carrier_name is None:
        missing_fields.append("carrier name")
    if expected_arrival is None and dispatch_status != "delivered":
        missing_fields.append("planned arrival")
    if latest.actual_departure_at is None and dispatch_status == "inland_dispatched":
        missing_fields.append("actual departure")
    confidence, reasons = evaluate_confidence(
        freshness=freshness,
        total_fields=4,
        present_fields=4 - len(missing_fields),
        has_conflict=False,
        missing_fields=missing_fields,
    )
    if inland_delay_flag:
        reasons.append("Inland delay heuristic is active.")
    if stale_record:
        reasons.append("Inland movement stream needs a refresh.")

    return InlandMonitoringItem(
        shipment_id=shipment.shipment_id,
        plant_id=shipment.plant_id,
        plant_name=movement_ctx.plant_name,
        material_id=shipment.material_id,
        material_name=movement_ctx.material_name,
        dispatch_status=dispatch_status,
        transporter_name=latest.carrier_name,
        expected_arrival=expected_arrival,
        actual_arrival=actual_arrival,
        inland_delay_flag=inland_delay_flag,
        stale_record=stale_record,
        missing_supporting_signal=missing_supporting_signal,
        freshness=freshness_info(freshness),
        confidence=confidence,
        confidence_reasons=reasons,
    )


def inland_delay_flag_for(latest: InlandMovement) -> bool:
    now = datetime.now(UTC)
    planned_arrival = ensure_optional_utc(latest.planned_arrival_at)
    actual_arrival = ensure_optional_utc(latest.actual_arrival_at)
    if planned_arrival and actual_arrival and actual_arrival > planned_arrival:
        return True
    if planned_arrival and actual_arrival is None and planned_arrival < now:
        return True
    return False


def movement_context_by_shipment_id(
    db: Session,
    tenant_id: int,
    shipment_id: str,
) -> ShipmentMovementContext | None:
    shipment = db.scalar(
        select(Shipment).where(
            Shipment.tenant_id == tenant_id,
            Shipment.shipment_id == shipment_id,
        )
    )
    if shipment is None:
        return None
    return build_context(db, shipment)


def shipment_contexts(
    db: Session,
    tenant_id: int,
    *,
    plant_id: int | None = None,
    material_id: int | None = None,
    shipment_id: str | None = None,
) -> list[ShipmentMovementContext]:
    query = select(Shipment).where(Shipment.tenant_id == tenant_id)
    if plant_id is not None:
        query = query.where(Shipment.plant_id == plant_id)
    if material_id is not None:
        query = query.where(Shipment.material_id == material_id)
    if shipment_id:
        term = f"%{shipment_id.lower()}%"
        query = query.where(
            or_(
                Shipment.shipment_id.ilike(term),
                Shipment.vessel_name.ilike(term),
            )
        )
    shipments = list(db.scalars(query.order_by(Shipment.current_eta)))
    return [build_context(db, shipment) for shipment in shipments]


def build_context(db: Session, shipment: Shipment) -> ShipmentMovementContext:
    plant = db.scalar(select(Plant).where(Plant.id == shipment.plant_id))
    material = db.scalar(select(Material).where(Material.id == shipment.material_id))
    port_events = list(
        db.scalars(
            select(PortEvent)
            .where(
                PortEvent.tenant_id == shipment.tenant_id,
                PortEvent.shipment_id == shipment.id,
            )
            .order_by(PortEvent.updated_at.desc())
        )
    )
    inland_movements = list(
        db.scalars(
            select(InlandMovement)
            .where(
                InlandMovement.tenant_id == shipment.tenant_id,
                InlandMovement.shipment_id == shipment.id,
            )
            .order_by(InlandMovement.updated_at.desc())
        )
    )
    return ShipmentMovementContext(
        shipment=shipment,
        plant_name=plant.name if plant else f"Plant {shipment.plant_id}",
        material_name=material.name if material else f"Material {shipment.material_id}",
        port_events=port_events,
        inland_movements=inland_movements,
    )


def movement_gaps(
    movement_ctx: ShipmentMovementContext,
    port_summary: PortMonitoringItem | None,
    inland_summary: InlandMonitoringItem | None,
) -> list[str]:
    gaps: list[str] = []
    if port_summary is None:
        gaps.append("No port event feed is available for this shipment.")
    elif port_summary.missing_supporting_signal:
        gaps.append("Port operations are missing discharge-supporting fields.")

    if inland_summary is None:
        gaps.append("No inland movement feed is available for this shipment.")
    elif inland_summary.missing_supporting_signal:
        gaps.append("Inland movement milestones are incomplete.")

    if movement_ctx.port_events and not movement_ctx.inland_movements:
        latest_port = movement_ctx.port_events[0]
        if latest_port.discharge_started_at:
            gaps.append("Discharge has started but inland dispatch has not been recorded yet.")
    return gaps


def movement_notes(
    port_summary: PortMonitoringItem | None,
    inland_summary: InlandMonitoringItem | None,
    missing_signals: list[str],
) -> list[str]:
    notes: list[str] = []
    if port_summary:
        notes.append(
            f"Latest port view is {port_summary.port_status.replace('_', ' ')} with "
            f"{port_summary.confidence} confidence."
        )
    if inland_summary:
        notes.append(
            f"Latest inland view is {inland_summary.dispatch_status.replace('_', ' ')} with "
            f"{inland_summary.confidence} confidence."
        )
    if not port_summary and not inland_summary:
        notes.append("Only shipment master data is available after vessel arrival.")
    notes.extend(missing_signals)
    return notes


def combined_freshness(
    port_summary: PortMonitoringItem | None,
    inland_summary: InlandMonitoringItem | None,
) -> FreshnessAssessment:
    timestamps = [
        summary.freshness.last_updated_at
        for summary in (port_summary, inland_summary)
        if summary and summary.freshness.last_updated_at is not None
    ]
    if not timestamps:
        return assess_freshness(None)
    return assess_freshness(max(timestamps))


def combined_confidence(
    port_summary: PortMonitoringItem | None,
    inland_summary: InlandMonitoringItem | None,
) -> str:
    levels = [summary.confidence for summary in (port_summary, inland_summary) if summary]
    if not levels:
        return "low"
    if "low" in levels:
        return "low"
    if all(level == "high" for level in levels):
        return "high"
    return "medium"


def freshness_info(freshness: FreshnessAssessment) -> FreshnessInfo:
    return FreshnessInfo(
        last_updated_at=freshness.last_updated_at,
        freshness_hours=freshness.freshness_hours,
        freshness_label=freshness.freshness_label,
    )


def normalize_state(value: str | None) -> str:
    if not value:
        return "unknown"
    return value.lower().strip().replace(" ", "_")
