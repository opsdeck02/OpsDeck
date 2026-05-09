from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session

from app.models import OperationalEvent
from app.models.enums import OperationalEventCategory, OperationalEventType
from app.schemas.context import RequestContext


class ContinuityTimelineEntry(BaseModel):
    timestamp: datetime
    event_type: str
    event_category: str
    title: str
    description: str
    plant_reference: str | None = None
    material_reference: str | None = None
    shipment_reference: str | None = None
    supplier_reference: str | None = None
    previous_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    confidence_score: Decimal | None = None
    freshness_status: str | None = None
    source_type: str
    source_reference: str | None = None
    event_id: int


class ContinuityTimelineFilters(BaseModel):
    plant_reference: str | None = None
    material_reference: str | None = None
    shipment_reference: str | None = None
    event_category: OperationalEventCategory | str | None = None
    since: datetime | None = None
    until: datetime | None = None


def build_continuity_timeline(
    db: Session,
    context: RequestContext,
    *,
    filters: ContinuityTimelineFilters | None = None,
) -> list[ContinuityTimelineEntry]:
    scoped_filters = filters or ContinuityTimelineFilters()
    events = list(db.scalars(timeline_query(context, scoped_filters)))
    return [timeline_entry_from_event(event) for event in events]


def build_timeline_for_risk_candidate(
    db: Session,
    context: RequestContext,
    risk_candidate: Any,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[ContinuityTimelineEntry]:
    events = list(db.scalars(risk_context_query(context, risk_candidate, since, until)))
    return [timeline_entry_from_event(event) for event in events]


def timeline_query(
    context: RequestContext,
    filters: ContinuityTimelineFilters,
):
    statement = select(OperationalEvent).where(OperationalEvent.tenant_id == context.tenant_id)
    if filters.plant_reference:
        statement = statement.where(OperationalEvent.plant_reference == filters.plant_reference)
    if filters.material_reference:
        statement = statement.where(
            OperationalEvent.material_reference == filters.material_reference
        )
    if filters.shipment_reference:
        statement = statement.where(
            OperationalEvent.shipment_reference == filters.shipment_reference
        )
    if filters.event_category:
        statement = statement.where(
            OperationalEvent.event_category == normalize_category(filters.event_category)
        )
    if filters.since:
        statement = statement.where(OperationalEvent.occurred_at >= filters.since)
    if filters.until:
        statement = statement.where(OperationalEvent.occurred_at <= filters.until)
    return statement.order_by(OperationalEvent.occurred_at, OperationalEvent.id)


def risk_context_query(
    context: RequestContext,
    risk_candidate: Any,
    since: datetime | None,
    until: datetime | None,
):
    statement = select(OperationalEvent).where(OperationalEvent.tenant_id == context.tenant_id)
    context_clauses = []
    source_event_ids = getattr(risk_candidate, "source_event_ids", None) or []
    if source_event_ids:
        context_clauses.append(OperationalEvent.id.in_(source_event_ids))

    shipment_reference = getattr(risk_candidate, "shipment_reference", None)
    if shipment_reference:
        context_clauses.append(OperationalEvent.shipment_reference == shipment_reference)

    plant_reference = getattr(risk_candidate, "plant_reference", None)
    material_reference = getattr(risk_candidate, "material_reference", None)
    if plant_reference and material_reference:
        context_clauses.append(
            (OperationalEvent.plant_reference == plant_reference)
            & (OperationalEvent.material_reference == material_reference)
        )
    elif plant_reference:
        context_clauses.append(OperationalEvent.plant_reference == plant_reference)
    elif material_reference:
        context_clauses.append(OperationalEvent.material_reference == material_reference)

    if context_clauses:
        statement = statement.where(or_(*context_clauses))
    else:
        statement = statement.where(false())

    if since:
        statement = statement.where(OperationalEvent.occurred_at >= since)
    if until:
        statement = statement.where(OperationalEvent.occurred_at <= until)
    return statement.order_by(OperationalEvent.occurred_at, OperationalEvent.id)


def timeline_entry_from_event(event: OperationalEvent) -> ContinuityTimelineEntry:
    return ContinuityTimelineEntry(
        timestamp=event.occurred_at,
        event_type=event.event_type.value,
        event_category=event.event_category.value,
        title=title_for_event(event),
        description=description_for_event(event),
        plant_reference=event.plant_reference,
        material_reference=event.material_reference,
        shipment_reference=event.shipment_reference,
        supplier_reference=event.supplier_reference,
        previous_value=event.previous_value,
        new_value=event.new_value,
        confidence_score=event.confidence_score,
        freshness_status=event.freshness_status.value if event.freshness_status else None,
        source_type=event.source_type.value,
        source_reference=event.source_reference,
        event_id=event.id,
    )


def title_for_event(event: OperationalEvent) -> str:
    titles = {
        OperationalEventType.INVENTORY_STOCK_UPDATED: "Inventory Stock Updated",
        OperationalEventType.SHIPMENT_ETA_CHANGED: "Shipment ETA Changed",
        OperationalEventType.SHIPMENT_MILESTONE_UPDATED: "Shipment Milestone Updated",
        OperationalEventType.SHIPMENT_DELAY_DETECTED: "Shipment Delay Detected",
        OperationalEventType.DATA_SOURCE_STALE_SIGNAL: "Data Source Stale",
        OperationalEventType.PLANNING_CONSUMPTION_UPDATED: "Planning Consumption Updated",
    }
    return titles.get(event.event_type, event.event_type.value.replace("_", " ").title())


def description_for_event(event: OperationalEvent) -> str:
    material = event.material_reference or "unknown material"
    plant = event.plant_reference or "unknown plant"
    shipment = event.shipment_reference or "unknown shipment"
    if event.event_type == OperationalEventType.INVENTORY_STOCK_UPDATED:
        return f"Inventory signal updated for material {material} at plant {plant}."
    if event.event_type == OperationalEventType.SHIPMENT_ETA_CHANGED:
        previous_eta = value_from(event.previous_value, "current_eta", "eta")
        new_eta = value_from(event.new_value, "current_eta", "eta")
        return f"Shipment {shipment} ETA changed from {previous_eta} to {new_eta}."
    if event.event_type == OperationalEventType.SHIPMENT_MILESTONE_UPDATED:
        milestone = value_from(event.new_value, "current_milestone", "current_state", "milestone")
        return f"Shipment {shipment} milestone updated to {milestone}."
    if event.event_type == OperationalEventType.SHIPMENT_DELAY_DETECTED:
        return f"Shipment {shipment} delay signal detected."
    if event.event_type == OperationalEventType.DATA_SOURCE_STALE_SIGNAL:
        return "Data source freshness degraded."
    if event.event_type == OperationalEventType.PLANNING_CONSUMPTION_UPDATED:
        return f"Consumption assumption changed for material {material}."
    return "Operational signal recorded."


def value_from(payload: dict[str, Any] | None, *keys: str) -> Any:
    if not payload:
        return "unknown"
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return "unknown"


def normalize_category(
    value: OperationalEventCategory | str,
) -> OperationalEventCategory:
    if isinstance(value, OperationalEventCategory):
        return value
    return OperationalEventCategory(value)
