from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    LineStopIncident,
    Material,
    Plant,
    PlantMaterialThreshold,
    Shipment,
    StockSnapshot,
)
from app.modules.line_stops.schemas import (
    HistoricalValidationIncidentResult,
    HistoricalValidationReport,
    LineStopIncidentCreate,
    LineStopIncidentListResponse,
    LineStopIncidentOut,
)
from app.modules.stock.time_phased_cover import (
    TimePhasedCoverInputs,
    TimePhasedInbound,
    evaluate_time_phased_cover,
)
from app.schemas.context import RequestContext


def create_line_stop_incident(
    db: Session,
    context: RequestContext,
    payload: LineStopIncidentCreate,
) -> LineStopIncidentOut:
    plant = db.scalar(
        select(Plant).where(Plant.id == payload.plant_id, Plant.tenant_id == context.tenant_id)
    )
    material = db.scalar(
        select(Material).where(
            Material.id == payload.material_id,
            Material.tenant_id == context.tenant_id,
        )
    )
    if plant is None or material is None:
        raise ValueError("Plant or material was not found for this tenant")

    incident = LineStopIncident(
        tenant_id=context.tenant_id,
        plant_id=plant.id,
        material_id=material.id,
        stopped_at=ensure_utc(payload.stopped_at),
        duration_hours=quantize_decimal(payload.duration_hours),
        notes=payload.notes.strip() if payload.notes else None,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return serialize_incident(db, incident)


def list_line_stop_incidents(
    db: Session,
    context: RequestContext,
    *,
    limit: int = 25,
) -> LineStopIncidentListResponse:
    items = list(
        db.scalars(
            select(LineStopIncident)
            .where(LineStopIncident.tenant_id == context.tenant_id)
            .order_by(LineStopIncident.stopped_at.desc())
            .limit(limit)
        )
    )
    total_duration = sum(
        (item.duration_hours for item in items),
        start=Decimal("0"),
    )
    return LineStopIncidentListResponse(
        total_incidents=len(items),
        total_duration_hours=quantize_decimal(total_duration),
        items=[serialize_incident(db, item) for item in items],
    )


def build_historical_validation_report(
    db: Session,
    context: RequestContext,
    *,
    limit: int = 25,
) -> HistoricalValidationReport:
    incidents = list(
        db.scalars(
            select(LineStopIncident)
            .where(LineStopIncident.tenant_id == context.tenant_id)
            .order_by(LineStopIncident.stopped_at.desc())
            .limit(limit)
        )
    )
    results = [
        validate_historical_incident(db, context, incident)
        for incident in incidents
    ]
    lead_times = [
        result.lead_time_gained_hours
        for result in results
        if result.lead_time_gained_hours is not None
    ]
    average_lead_time = (
        quantize_decimal(sum(lead_times, start=Decimal("0")) / Decimal(len(lead_times)))
        if lead_times
        else None
    )
    return HistoricalValidationReport(
        total_incidents=len(results),
        incidents_with_warning=sum(
            1 for result in results if result.predicted_warning_date is not None
        ),
        incidents_missed=sum(1 for result in results if result.predicted_warning_date is None),
        average_lead_time_hours=average_lead_time,
        results=results,
    )


def validate_historical_incident(
    db: Session,
    context: RequestContext,
    incident: LineStopIncident,
) -> HistoricalValidationIncidentResult:
    plant = db.get(Plant, incident.plant_id)
    material = db.get(Material, incident.material_id)
    incident_time = ensure_utc(incident.stopped_at)
    missed_signals: list[str] = []
    snapshot = db.scalar(
        select(StockSnapshot)
        .where(
            StockSnapshot.tenant_id == context.tenant_id,
            StockSnapshot.plant_id == incident.plant_id,
            StockSnapshot.material_id == incident.material_id,
            StockSnapshot.snapshot_time <= incident_time,
        )
        .order_by(StockSnapshot.snapshot_time.desc())
    )
    threshold = db.scalar(
        select(PlantMaterialThreshold).where(
            PlantMaterialThreshold.tenant_id == context.tenant_id,
            PlantMaterialThreshold.plant_id == incident.plant_id,
            PlantMaterialThreshold.material_id == incident.material_id,
        )
    )
    if snapshot is None:
        missed_signals.append("No stock snapshot existed before the incident date.")
        return HistoricalValidationIncidentResult(
            incident_id=incident.id,
            plant_id=incident.plant_id,
            plant_name=plant.name if plant else f"Plant {incident.plant_id}",
            material_id=incident.material_id,
            material_name=material.name if material else f"Material {incident.material_id}",
            incident_date=incident_time,
            predicted_warning_date=None,
            lead_time_gained_hours=None,
            missed_signals=missed_signals,
            confidence_level="low",
            calibration_status="UNCALIBRATED",
        )
    if threshold is None:
        missed_signals.append("Continuity thresholds were missing for the incident context.")
    if snapshot.daily_consumption_mt <= 0:
        missed_signals.append("Daily consumption was missing or invalid before the incident.")
        return HistoricalValidationIncidentResult(
            incident_id=incident.id,
            plant_id=incident.plant_id,
            plant_name=plant.name if plant else f"Plant {incident.plant_id}",
            material_id=incident.material_id,
            material_name=material.name if material else f"Material {incident.material_id}",
            incident_date=incident_time,
            predicted_warning_date=None,
            lead_time_gained_hours=None,
            missed_signals=missed_signals,
            confidence_level="low",
            calibration_status="UNCALIBRATED",
        )

    shipments = historical_inbounds(db, context, incident, incident_time)
    if not shipments:
        missed_signals.append("No linked inbound shipments were available before incident.")
    cover = evaluate_time_phased_cover(
        TimePhasedCoverInputs(
            snapshot_time=snapshot.snapshot_time,
            usable_stock_mt=snapshot.available_to_consume_mt,
            daily_consumption_mt=snapshot.daily_consumption_mt,
            warning_days=threshold.warning_days if threshold else None,
            critical_days=threshold.threshold_days if threshold else None,
            reserve_days=threshold.minimum_buffer_stock_days if threshold else None,
            reserve_quantity_mt=threshold.minimum_buffer_stock_mt if threshold else None,
            supplier_context_complete=all(item.supplier_linked for item in shipments),
            inbounds=tuple(shipments),
        )
    )
    predicted = cover.warning_date
    lead_time = None
    if predicted is None:
        missed_signals.append("OpsDeck did not produce a warning date for this incident.")
    elif ensure_utc(predicted) > incident_time:
        missed_signals.append("Predicted warning date was after the recorded incident.")
    else:
        lead_time = quantize_decimal(
            Decimal(str((incident_time - ensure_utc(predicted)).total_seconds()))
            / Decimal("3600")
        )
    return HistoricalValidationIncidentResult(
        incident_id=incident.id,
        plant_id=incident.plant_id,
        plant_name=plant.name if plant else f"Plant {incident.plant_id}",
        material_id=incident.material_id,
        material_name=material.name if material else f"Material {incident.material_id}",
        incident_date=incident_time,
        predicted_warning_date=predicted,
        lead_time_gained_hours=lead_time,
        missed_signals=missed_signals,
        confidence_level=confidence_from_score(cover.confidence_score),
        calibration_status=cover.calibration_status,
    )


def historical_inbounds(
    db: Session,
    context: RequestContext,
    incident: LineStopIncident,
    incident_time: datetime,
) -> list[TimePhasedInbound]:
    shipments = db.scalars(
        select(Shipment)
        .where(
            Shipment.tenant_id == context.tenant_id,
            Shipment.plant_id == incident.plant_id,
            Shipment.material_id == incident.material_id,
            Shipment.current_eta >= incident_time - timedelta(days=30),
            Shipment.latest_update_at <= incident_time,
        )
        .order_by(Shipment.current_eta.asc())
    )
    return [
        TimePhasedInbound(
            shipment_id=shipment.shipment_id,
            supplier_name=shipment.supplier_name,
            eta=shipment.current_eta,
            raw_quantity_mt=shipment.quantity_mt,
            effective_quantity_mt=shipment.quantity_mt,
            supplier_linked=shipment.supplier_id is not None,
        )
        for shipment in shipments
    ]


def confidence_from_score(score: Decimal) -> str:
    if score >= Decimal("0.80"):
        return "high"
    if score >= Decimal("0.55"):
        return "medium"
    return "low"


def serialize_incident(db: Session, incident: LineStopIncident) -> LineStopIncidentOut:
    plant = db.get(Plant, incident.plant_id)
    material = db.get(Material, incident.material_id)
    return LineStopIncidentOut(
        id=incident.id,
        plant_id=incident.plant_id,
        plant_name=plant.name if plant else f"Plant {incident.plant_id}",
        material_id=incident.material_id,
        material_name=material.name if material else f"Material {incident.material_id}",
        stopped_at=ensure_utc(incident.stopped_at),
        duration_hours=quantize_decimal(incident.duration_hours),
        notes=incident.notes,
        created_at=ensure_utc(incident.created_at),
    )


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
