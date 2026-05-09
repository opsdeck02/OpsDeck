from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import OperationalEvent
from app.models.enums import (
    OperationalEventCategory,
    OperationalEventSourceType,
    OperationalEventType,
)
from app.modules.operational_events.confidence import calculate_confidence
from app.modules.operational_events.freshness import classify_event_freshness
from app.modules.operational_events.schemas import OperationalEventCreate


def create_operational_event(db: Session, payload: OperationalEventCreate) -> OperationalEvent:
    detected_at = payload.detected_at or datetime.now(UTC)
    occurred_at = payload.occurred_at or detected_at
    metadata = sanitize_json(payload.metadata) or {}
    confidence = calculate_confidence(payload, detected_at)
    freshness = classify_event_freshness(
        occurred_at=payload.occurred_at,
        detected_at=detected_at,
        source_type=payload.source_type,
    )
    metadata["confidence"] = {
        "score": float(confidence.score),
        "factors": confidence.factors,
        "reasons": confidence.reasons,
    }
    metadata["freshness"] = {
        "status": freshness.status.value,
        "age_minutes": freshness.age_minutes,
        "source_type": freshness.source_type,
        "threshold_profile": freshness.threshold_profile,
        "reasons": freshness.reasons,
    }
    event = OperationalEvent(
        tenant_id=payload.tenant_id,
        event_type=payload.event_type,
        event_category=payload.event_category,
        source_type=payload.source_type,
        source_id=payload.source_id,
        source_reference=payload.source_reference,
        occurred_at=occurred_at,
        detected_at=detected_at,
        plant_id=payload.plant_id,
        plant_reference=payload.plant_reference,
        material_id=payload.material_id,
        material_reference=payload.material_reference,
        shipment_id=payload.shipment_id,
        shipment_reference=payload.shipment_reference,
        supplier_id=payload.supplier_id,
        supplier_reference=payload.supplier_reference,
        purchase_order_reference=payload.purchase_order_reference,
        quantity_value=payload.quantity_value,
        quantity_unit=payload.quantity_unit,
        previous_value=sanitize_json(payload.previous_value),
        new_value=sanitize_json(payload.new_value),
        metadata_json=metadata,
        confidence_score=payload.confidence_score or confidence.score,
        freshness_status=payload.freshness_status or freshness.status,
    )
    db.add(event)
    return event


def sanitize_json(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return {key: sanitize_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def source_type_from_reference(source_reference: str | None) -> OperationalEventSourceType:
    if not source_reference:
        return OperationalEventSourceType.UNKNOWN
    normalized = source_reference.strip().lower()
    try:
        return OperationalEventSourceType(normalized)
    except ValueError:
        pass
    if normalized in {"google_sheets", "excel_online", "microsoft_graph"}:
        return OperationalEventSourceType.EXTERNAL_DATA_SOURCE
    if normalized in {"manual_upload", "upload"}:
        return OperationalEventSourceType.MANUAL_UPLOAD
    if normalized in {"file_upload", "file_ingestion"}:
        return OperationalEventSourceType.FILE_INGESTION
    if normalized in {"email", "email_ingestion"}:
        return OperationalEventSourceType.EMAIL_INGESTION
    return OperationalEventSourceType.UNKNOWN


def emit_inventory_stock_updated(
    db: Session,
    *,
    tenant_id: int,
    occurred_at: datetime,
    source_reference: str | None,
    plant_id: int,
    plant_reference: str,
    material_id: int,
    material_reference: str,
    quantity_value: Decimal | None,
    previous_value: dict[str, Any] | None,
    new_value: dict[str, Any],
    source_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> OperationalEvent:
    return create_operational_event(
        db,
        OperationalEventCreate(
            tenant_id=tenant_id,
            event_type=OperationalEventType.INVENTORY_STOCK_UPDATED,
            event_category=OperationalEventCategory.INVENTORY,
            source_type=source_type_from_reference(source_reference),
            source_id=source_id,
            source_reference=source_reference,
            occurred_at=occurred_at,
            plant_id=plant_id,
            plant_reference=plant_reference,
            material_id=material_id,
            material_reference=material_reference,
            quantity_value=quantity_value,
            quantity_unit="MT",
            previous_value=previous_value,
            new_value=new_value,
            metadata=metadata,
        ),
    )


def emit_shipment_update_event(
    db: Session,
    *,
    tenant_id: int,
    event_type: OperationalEventType,
    occurred_at: datetime,
    source_reference: str | None,
    shipment_id: int,
    shipment_reference: str,
    plant_id: int,
    plant_reference: str,
    material_id: int,
    material_reference: str,
    supplier_id,
    supplier_reference: str | None,
    quantity_value: Decimal | None,
    previous_value: dict[str, Any] | None,
    new_value: dict[str, Any],
    source_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> OperationalEvent:
    return create_operational_event(
        db,
        OperationalEventCreate(
            tenant_id=tenant_id,
            event_type=event_type,
            event_category=OperationalEventCategory.SHIPMENT,
            source_type=source_type_from_reference(source_reference),
            source_id=source_id,
            source_reference=source_reference,
            occurred_at=occurred_at,
            shipment_id=shipment_id,
            shipment_reference=shipment_reference,
            plant_id=plant_id,
            plant_reference=plant_reference,
            material_id=material_id,
            material_reference=material_reference,
            supplier_id=supplier_id,
            supplier_reference=supplier_reference,
            quantity_value=quantity_value,
            quantity_unit="MT",
            previous_value=previous_value,
            new_value=new_value,
            metadata=metadata,
        ),
    )
