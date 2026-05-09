from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContinuityRiskSnapshot
from app.modules.exposure.mapping import OperationalExposureMapping
from app.modules.risk_snapshots.schemas import ContinuityRiskSnapshotCreate
from app.modules.rules.engine import RiskCandidate
from app.modules.shipments.schemas import ShipmentContinuityResult
from app.modules.stock.schemas import InventoryContinuityResult
from app.schemas.context import RequestContext


def risk_fingerprint(
    *,
    tenant_id: int,
    risk_type: str,
    plant_reference: str | None,
    material_reference: str | None,
    shipment_reference: str | None = None,
) -> str:
    parts = [
        str(tenant_id),
        normalize_part(risk_type),
        normalize_part(plant_reference),
        normalize_part(material_reference),
        normalize_part(shipment_reference),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def create_snapshot_from_risk_candidate(
    db: Session,
    context: RequestContext,
    candidate: RiskCandidate,
    *,
    snapshot_time: datetime | None = None,
    exposure: OperationalExposureMapping | None = None,
    inventory_continuity: InventoryContinuityResult | None = None,
    shipment_continuity: ShipmentContinuityResult | None = None,
    metadata: dict[str, Any] | None = None,
) -> ContinuityRiskSnapshot:
    captured_at = ensure_utc(snapshot_time or datetime.now(UTC))
    payload = snapshot_payload_from_candidate(
        context,
        candidate,
        snapshot_time=captured_at,
        exposure=exposure,
        inventory_continuity=inventory_continuity,
        shipment_continuity=shipment_continuity,
        metadata=metadata,
    )
    return upsert_snapshot(db, payload)


def snapshot_payload_from_candidate(
    context: RequestContext,
    candidate: RiskCandidate,
    *,
    snapshot_time: datetime,
    exposure: OperationalExposureMapping | None = None,
    inventory_continuity: InventoryContinuityResult | None = None,
    shipment_continuity: ShipmentContinuityResult | None = None,
    metadata: dict[str, Any] | None = None,
) -> ContinuityRiskSnapshotCreate:
    plant_reference = candidate.plant_reference or exposure_plant(exposure)
    material_reference = candidate.material_reference or exposure_material(exposure)
    shipment_reference = candidate.shipment_reference or exposure_shipment(exposure)
    fingerprint = risk_fingerprint(
        tenant_id=context.tenant_id,
        risk_type=candidate.risk_type,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
    )
    merged_metadata = {
        "rule_reasons": list(candidate.rule_reasons),
        "continuity_status": candidate.continuity_status,
        "recommended_owner_role": candidate.recommended_owner_role,
    }
    if metadata:
        merged_metadata.update(metadata)

    return ContinuityRiskSnapshotCreate(
        tenant_id=context.tenant_id,
        risk_fingerprint=fingerprint,
        risk_type=candidate.risk_type,
        severity=candidate.severity,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
        supplier_reference=candidate.supplier_reference,
        snapshot_time=snapshot_time,
        days_of_cover=candidate.days_of_cover or inventory_days_of_cover(inventory_continuity),
        projected_exhaustion_date=(
            candidate.projected_exhaustion_date
            or inventory_projected_exhaustion(inventory_continuity)
            or exposure_projected_exhaustion(exposure)
        ),
        exposure_level=exposure.exposure_level if exposure is not None else None,
        exposure_basis=exposure.exposure_basis if exposure is not None else None,
        exposure_value=decimal_from_metadata(metadata, "exposure_value"),
        shipment_delay_hours=shipment_delay_hours(shipment_continuity),
        tracking_freshness_minutes=decimal_from_metadata(metadata, "tracking_freshness_minutes"),
        freshness_status=candidate.freshness_status or shipment_freshness(shipment_continuity),
        confidence_score=candidate.confidence_score,
        usable_stock=inventory_continuity.usable_quantity if inventory_continuity is not None else None,
        blocked_stock=inventory_continuity.blocked_quantity if inventory_continuity is not None else None,
        incoming_quantity=incoming_quantity(inventory_continuity),
        escalation_state=None,
        escalation_score=None,
        escalation_reason=None,
        source_event_ids=list(candidate.source_event_ids) if candidate.source_event_ids else None,
        metadata=merged_metadata,
    )


def upsert_snapshot(
    db: Session,
    payload: ContinuityRiskSnapshotCreate,
) -> ContinuityRiskSnapshot:
    if db.new:
        db.flush()
    existing = db.scalar(
        select(ContinuityRiskSnapshot).where(
            ContinuityRiskSnapshot.tenant_id == payload.tenant_id,
            ContinuityRiskSnapshot.risk_fingerprint == payload.risk_fingerprint,
            ContinuityRiskSnapshot.snapshot_time == payload.snapshot_time,
        )
    )
    values = model_values(payload)
    if existing is not None:
        for key, value in values.items():
            setattr(existing, key, value)
        return existing

    snapshot = ContinuityRiskSnapshot(**values)
    db.add(snapshot)
    return snapshot


def model_values(payload: ContinuityRiskSnapshotCreate) -> dict[str, Any]:
    values = payload.model_dump()
    values["metadata_json"] = values.pop("metadata")
    return values


def normalize_part(value: str | None) -> str:
    if value is None or value == "":
        return "<none>"
    return value.strip().lower()


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def exposure_plant(exposure: OperationalExposureMapping | None) -> str | None:
    return exposure.plant_reference if exposure is not None else None


def exposure_material(exposure: OperationalExposureMapping | None) -> str | None:
    return exposure.material_reference if exposure is not None else None


def exposure_shipment(exposure: OperationalExposureMapping | None) -> str | None:
    return exposure.shipment_reference if exposure is not None else None


def exposure_projected_exhaustion(
    exposure: OperationalExposureMapping | None,
) -> datetime | None:
    return exposure.estimated_exposure_date if exposure is not None else None


def inventory_days_of_cover(
    inventory: InventoryContinuityResult | None,
) -> Decimal | None:
    return inventory.days_of_cover if inventory is not None else None


def inventory_projected_exhaustion(
    inventory: InventoryContinuityResult | None,
) -> datetime | None:
    return inventory.projected_exhaustion_date if inventory is not None else None


def incoming_quantity(
    inventory: InventoryContinuityResult | None,
) -> Decimal | None:
    if inventory is None:
        return None
    return inventory.inbound_committed_quantity + inventory.inbound_uncertain_quantity


def shipment_delay_hours(
    shipment: ShipmentContinuityResult | None,
) -> Decimal | None:
    if shipment is None or shipment.eta_slip_days is None:
        return None
    return shipment.eta_slip_days * Decimal("24")


def shipment_freshness(shipment: ShipmentContinuityResult | None) -> str | None:
    return shipment.tracking_freshness_status if shipment is not None else None


def decimal_from_metadata(
    metadata: dict[str, Any] | None,
    key: str,
) -> Decimal | None:
    if not metadata or metadata.get(key) is None:
        return None
    return Decimal(str(metadata[key]))
