from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LineStopIncident, Material, Plant
from app.modules.line_stops.schemas import (
    LineStopIncidentCreate,
    LineStopIncidentListResponse,
    LineStopIncidentOut,
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
