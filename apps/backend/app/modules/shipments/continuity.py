from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, Plant, Shipment
from app.models.enums import OperationalEventSourceType, ShipmentState
from app.modules.operational_events.freshness import classify_event_freshness
from app.modules.shipments.schemas import ShipmentContinuityResult
from app.modules.shipments.visibility_confidence import calculate_visibility_confidence
from app.schemas.context import RequestContext

WATCH_STATUSES = {"watch"}
DEGRADED_FRESHNESS_STATUSES = {"stale", "critical"}


def calculate_shipment_continuity(
    *,
    shipment_reference: str,
    eta: datetime | None,
    previous_eta: datetime | None = None,
    planned_eta: datetime | None = None,
    current_milestone: str | None = None,
    tracking_updated_at: datetime | None = None,
    tracking_source_type: OperationalEventSourceType = OperationalEventSourceType.AIS,
    linked_purchase_order_reference: str | None = None,
    linked_material_reference: str | None = None,
    linked_plant_reference: str | None = None,
    current_state: ShipmentState | str | None = None,
    now: datetime | None = None,
) -> ShipmentContinuityResult:
    evaluated_at = ensure_utc(now or datetime.now(UTC))
    continuity_reasons: list[str] = []
    missing_milestones: list[str] = []
    overdue_milestones: list[str] = []

    baseline_eta = previous_eta or planned_eta
    eta_slip_days = calculate_eta_slip_days(eta, baseline_eta)
    tracking_freshness_status = tracking_freshness(
        tracking_updated_at,
        evaluated_at,
        tracking_source_type,
    )

    if eta is None:
        continuity_reasons.append("Current ETA is missing")
        status = "unknown"
    else:
        status = "on_track"
        if eta_slip_days is not None and eta_slip_days > Decimal("0"):
            continuity_reasons.append(f"ETA slipped by {eta_slip_days} days")
            status = "watch" if eta_slip_days <= Decimal("1.00") else "degraded"
        else:
            continuity_reasons.append("No ETA slip detected")

    if not current_milestone:
        missing_milestones.append("current_milestone")
        continuity_reasons.append("Current milestone is missing")
        if status == "on_track":
            status = "watch"

    if eta is not None and ensure_utc(eta) < evaluated_at and not delivered(current_state):
        overdue_milestones.append("delivery")
        continuity_reasons.append("Delivery milestone is overdue against current ETA")
        status = "degraded"

    if tracking_freshness_status in DEGRADED_FRESHNESS_STATUSES:
        continuity_reasons.append(f"Tracking data is {tracking_freshness_status}")
        status = "degraded"
    elif tracking_freshness_status == "unknown":
        continuity_reasons.append("Tracking freshness is unknown")
        if status == "on_track":
            status = "watch"
    else:
        continuity_reasons.append(f"Tracking data is {tracking_freshness_status}")

    missing_context = missing_linked_context(
        linked_purchase_order_reference=linked_purchase_order_reference,
        linked_material_reference=linked_material_reference,
        linked_plant_reference=linked_plant_reference,
    )
    if missing_context:
        continuity_reasons.append(f"Missing linked context: {', '.join(missing_context)}")
        if status == "on_track":
            status = "watch"
    else:
        continuity_reasons.append(
            (
                f"Shipment is linked to plant {linked_plant_reference} "
                f"and material {linked_material_reference}"
            )
        )

    return ShipmentContinuityResult(
        shipment_reference=shipment_reference,
        status=status,
        eta=ensure_optional_utc(eta),
        previous_eta=ensure_optional_utc(baseline_eta),
        eta_slip_days=eta_slip_days,
        current_milestone=current_milestone,
        missing_milestones=missing_milestones,
        overdue_milestones=overdue_milestones,
        tracking_freshness_status=tracking_freshness_status,
        linked_purchase_order_reference=linked_purchase_order_reference,
        linked_material_reference=linked_material_reference,
        linked_plant_reference=linked_plant_reference,
        continuity_reasons=continuity_reasons,
    )


def calculate_shipment_continuity_for(
    db: Session,
    context: RequestContext,
    shipment_reference: str,
    *,
    now: datetime | None = None,
) -> ShipmentContinuityResult | None:
    shipment = db.scalar(
        select(Shipment).where(
            Shipment.tenant_id == context.tenant_id,
            Shipment.shipment_id == shipment_reference,
        )
    )
    if shipment is None:
        return None

    plant = db.scalar(
        select(Plant).where(
            Plant.tenant_id == context.tenant_id,
            Plant.id == shipment.plant_id,
        )
    )
    material = db.scalar(
        select(Material).where(
            Material.tenant_id == context.tenant_id,
            Material.id == shipment.material_id,
        )
    )
    tracking_updated_at = (
        shipment.last_tracking_update_at or shipment.latest_update_at or shipment.updated_at
    )
    result = calculate_shipment_continuity(
        shipment_reference=shipment.shipment_id,
        eta=shipment.current_eta,
        previous_eta=shipment.latest_eta,
        planned_eta=shipment.planned_eta,
        current_milestone=shipment.current_milestone,
        tracking_updated_at=tracking_updated_at,
        tracking_source_type=tracking_source_type_for(shipment),
        linked_purchase_order_reference=None,
        linked_material_reference=material.code if material else None,
        linked_plant_reference=plant.code if plant else None,
        current_state=shipment.current_state,
        now=now,
    )
    visibility = calculate_visibility_confidence(shipment, now=now)
    result.continuity_reasons.extend(
        reason
        for reason in visibility.reason_chain
        if reason.startswith("Shipment classified")
        or reason.startswith("ETA drift")
        or "ETA" in reason
        or "Confidence partially restored" in reason
    )
    return result


def calculate_eta_slip_days(
    eta: datetime | None,
    baseline_eta: datetime | None,
) -> Decimal | None:
    if eta is None or baseline_eta is None:
        return None
    slip_seconds = (ensure_utc(eta) - ensure_utc(baseline_eta)).total_seconds()
    if slip_seconds <= 0:
        return Decimal("0.00")
    return (Decimal(str(slip_seconds)) / Decimal("86400")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def tracking_freshness(
    tracking_updated_at: datetime | None,
    detected_at: datetime,
    source_type: OperationalEventSourceType,
) -> str:
    result = classify_event_freshness(
        occurred_at=tracking_updated_at,
        detected_at=detected_at,
        source_type=source_type,
    )
    return result.status.value


def tracking_source_type_for(shipment: Shipment) -> OperationalEventSourceType:
    if shipment.imo_number or shipment.mmsi or shipment.vessel_name:
        return OperationalEventSourceType.AIS
    return OperationalEventSourceType.MANUAL_UPLOAD


def missing_linked_context(
    *,
    linked_purchase_order_reference: str | None,
    linked_material_reference: str | None,
    linked_plant_reference: str | None,
) -> list[str]:
    missing = []
    if not linked_purchase_order_reference:
        missing.append("purchase_order_reference")
    if not linked_material_reference:
        missing.append("material_reference")
    if not linked_plant_reference:
        missing.append("plant_reference")
    return missing


def delivered(current_state: ShipmentState | str | None) -> bool:
    if current_state is None:
        return False
    value = current_state.value if isinstance(current_state, ShipmentState) else str(current_state)
    return value == ShipmentState.DELIVERED.value


def ensure_optional_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_utc(value)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
