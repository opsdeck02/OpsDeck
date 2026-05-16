from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, Plant, Shipment, StockSnapshot
from app.models.enums import OperationalEventSourceType, ShipmentState
from app.modules.operational_events.freshness import classify_event_freshness
from app.modules.stock.schemas import InventoryContinuityResult
from app.schemas.context import RequestContext

COMMITTED_INBOUND_STATES = {
    ShipmentState.IN_TRANSIT,
    ShipmentState.AT_PORT,
    ShipmentState.DISCHARGING,
    ShipmentState.INLAND_TRANSIT,
}

UNCERTAIN_INBOUND_STATES = {
    ShipmentState.PLANNED,
    ShipmentState.DELAYED,
}


def calculate_inventory_continuity(
    *,
    plant_reference: str,
    material_reference: str,
    on_hand_quantity: Decimal,
    daily_consumption_rate: Decimal | None,
    unit: str,
    reserved_quantity: Decimal | None = None,
    blocked_quantity: Decimal | None = None,
    quality_hold_quantity: Decimal | None = None,
    inbound_committed_quantity: Decimal | None = None,
    inbound_uncertain_quantity: Decimal | None = None,
    trusted_inbound_quantity: Decimal | None = None,
    uncertain_inbound_quantity: Decimal | None = None,
    cover_confidence_score: Decimal | None = None,
    freshness_status: str = "unknown",
    trust_warnings: list[str] | None = None,
    now: datetime | None = None,
) -> InventoryContinuityResult:
    reserved = reserved_quantity or Decimal("0")
    blocked = blocked_quantity or Decimal("0")
    quality_hold = quality_hold_quantity or Decimal("0")
    inbound_committed = inbound_committed_quantity or Decimal("0")
    inbound_uncertain = inbound_uncertain_quantity or Decimal("0")
    trusted_inbound = (
        trusted_inbound_quantity if trusted_inbound_quantity is not None else inbound_committed
    )
    uncertain_inbound = (
        uncertain_inbound_quantity if uncertain_inbound_quantity is not None else inbound_uncertain
    )
    usable_quantity = on_hand_quantity - reserved - blocked - quality_hold
    trusted_cover_quantity = usable_quantity + trusted_inbound
    calculation_reasons = [
        (
            "Usable stock calculated from on-hand minus reserved, blocked, "
            "and quality-hold quantities"
        )
    ]
    warnings = list(trust_warnings or [])

    days_of_cover: Decimal | None = None
    trusted_days_of_cover: Decimal | None = None
    projected_exhaustion_date: datetime | None = None
    if daily_consumption_rate is None or daily_consumption_rate <= 0:
        calculation_reasons.append(
            "Days of cover is unknown because daily consumption rate is missing, zero, or negative"
        )
        warnings.append("Trusted cover is unknown because consumption rate is missing.")
    else:
        days_of_cover = quantize_decimal(usable_quantity / daily_consumption_rate)
        calculation_reasons.append("Days of cover calculated using daily consumption rate")
        trusted_days_of_cover = quantize_decimal(trusted_cover_quantity / daily_consumption_rate)
        calculation_reasons.append("Trusted cover includes only inbound with reliable visibility")
        projected_exhaustion_date = ensure_utc(now or datetime.now(UTC)) + timedelta(
            days=float(trusted_days_of_cover)
        )
        calculation_reasons.append("Projected exhaustion date calculated from trusted cover")

    if usable_quantity < 0:
        calculation_reasons.append("Usable stock is negative after inventory adjustments")
    if uncertain_inbound > 0:
        warnings.append("Inbound contribution excluded from trusted cover due to weak visibility.")
    if cover_confidence_score is None:
        cover_confidence_score = Decimal("1.00") if not warnings else Decimal("0.70")

    return InventoryContinuityResult(
        plant_reference=plant_reference,
        material_reference=material_reference,
        on_hand_quantity=quantize_decimal(on_hand_quantity),
        reserved_quantity=quantize_decimal(reserved),
        blocked_quantity=quantize_decimal(blocked),
        quality_hold_quantity=quantize_decimal(quality_hold),
        usable_quantity=quantize_decimal(usable_quantity),
        inbound_committed_quantity=quantize_decimal(inbound_committed),
        inbound_uncertain_quantity=quantize_decimal(inbound_uncertain),
        raw_days_of_cover=days_of_cover,
        trusted_inbound_quantity=quantize_decimal(trusted_inbound),
        uncertain_inbound_quantity=quantize_decimal(uncertain_inbound),
        trusted_days_of_cover=trusted_days_of_cover,
        daily_consumption_rate=(
            quantize_decimal(daily_consumption_rate) if daily_consumption_rate is not None else None
        ),
        days_of_cover=days_of_cover,
        projected_exhaustion_date=projected_exhaustion_date,
        cover_confidence_score=quantize_decimal(cover_confidence_score),
        freshness_status=freshness_status,
        trust_warnings=dedupe(warnings),
        unit=unit,
        calculation_reasons=calculation_reasons,
    )


def calculate_inventory_continuity_for(
    db: Session,
    context: RequestContext,
    plant_id: int,
    material_id: int,
    *,
    now: datetime | None = None,
) -> InventoryContinuityResult | None:
    plant = db.scalar(
        select(Plant).where(
            Plant.tenant_id == context.tenant_id,
            Plant.id == plant_id,
        )
    )
    material = db.scalar(
        select(Material).where(
            Material.tenant_id == context.tenant_id,
            Material.id == material_id,
        )
    )
    if plant is None or material is None:
        return None

    snapshot = latest_snapshot(db, context.tenant_id, plant_id, material_id)
    if snapshot is None:
        return None

    trusted_inbound, uncertain_inbound, freshness_status, trust_warnings, cover_confidence_score = (
        trusted_inbound_quantities(
            db,
            context.tenant_id,
            plant_id,
            material_id,
            now=now,
        )
    )
    inbound_committed, inbound_uncertain = inbound_quantities(
        db,
        context.tenant_id,
        plant_id,
        material_id,
    )
    quality_hold = snapshot.quality_held_mt
    implied_blocked = implied_blocked_quantity(snapshot)
    return calculate_inventory_continuity(
        plant_reference=plant.code,
        material_reference=material.code,
        on_hand_quantity=snapshot.on_hand_mt,
        reserved_quantity=Decimal("0"),
        blocked_quantity=implied_blocked,
        quality_hold_quantity=quality_hold,
        inbound_committed_quantity=inbound_committed,
        inbound_uncertain_quantity=inbound_uncertain,
        trusted_inbound_quantity=trusted_inbound,
        uncertain_inbound_quantity=uncertain_inbound,
        cover_confidence_score=cover_confidence_score,
        freshness_status=freshness_status,
        trust_warnings=trust_warnings,
        daily_consumption_rate=snapshot.daily_consumption_mt,
        unit=material.uom,
        now=now,
    )


def latest_snapshot(
    db: Session,
    tenant_id: int,
    plant_id: int,
    material_id: int,
) -> StockSnapshot | None:
    return db.scalar(
        select(StockSnapshot)
        .where(
            StockSnapshot.tenant_id == tenant_id,
            StockSnapshot.plant_id == plant_id,
            StockSnapshot.material_id == material_id,
        )
        .order_by(StockSnapshot.snapshot_time.desc())
    )


def inbound_quantities(
    db: Session,
    tenant_id: int,
    plant_id: int,
    material_id: int,
) -> tuple[Decimal, Decimal]:
    committed = Decimal("0")
    uncertain = Decimal("0")
    shipments = db.scalars(
        select(Shipment).where(
            Shipment.tenant_id == tenant_id,
            Shipment.plant_id == plant_id,
            Shipment.material_id == material_id,
        )
    )
    for shipment in shipments:
        if shipment.current_state in COMMITTED_INBOUND_STATES:
            committed += shipment.quantity_mt
        elif shipment.current_state in UNCERTAIN_INBOUND_STATES:
            uncertain += shipment.quantity_mt
    return committed, uncertain


def trusted_inbound_quantities(
    db: Session,
    tenant_id: int,
    plant_id: int,
    material_id: int,
    *,
    now: datetime | None = None,
) -> tuple[Decimal, Decimal, str, list[str], Decimal]:
    evaluated_at = ensure_utc(now or datetime.now(UTC))
    trusted = Decimal("0")
    uncertain = Decimal("0")
    warnings: list[str] = []
    freshness_rank = {
        "fresh": 0,
        "delayed": 1,
        "aging": 2,
        "unknown": 3,
        "stale": 4,
        "critical": 5,
    }
    worst_freshness = "fresh"
    trusted_count = 0
    total_count = 0
    shipments = db.scalars(
        select(Shipment).where(
            Shipment.tenant_id == tenant_id,
            Shipment.plant_id == plant_id,
            Shipment.material_id == material_id,
        )
    )
    for shipment in shipments:
        total_count += 1
        trusted_shipment, reason, freshness = trusted_shipment_inbound(shipment, evaluated_at)
        if (
            freshness_rank.get(freshness, freshness_rank["unknown"])
            > freshness_rank[worst_freshness]
        ):
            worst_freshness = freshness
        if trusted_shipment:
            trusted += shipment.quantity_mt
            trusted_count += 1
        else:
            uncertain += shipment.quantity_mt
            if reason:
                warnings.append(reason)

    if total_count == 0:
        return Decimal("0"), Decimal("0"), "unknown", [], Decimal("1.00")
    confidence = Decimal(str(trusted_count)) / Decimal(str(total_count))
    if uncertain > 0:
        warnings.append("Inbound contribution excluded from trusted cover due to weak visibility.")
    return trusted, uncertain, worst_freshness, dedupe(warnings), quantize_decimal(confidence)


def trusted_shipment_inbound(
    shipment: Shipment, evaluated_at: datetime
) -> tuple[bool, str | None, str]:
    if shipment.plant_id is None or shipment.material_id is None:
        return (
            False,
            "Inbound contribution excluded because plant/material context is missing.",
            "unknown",
        )
    if shipment.current_eta is None:
        return False, "Inbound contribution excluded because ETA is missing.", "unknown"
    freshness = shipment_freshness(shipment, evaluated_at)
    if shipment.current_state not in COMMITTED_INBOUND_STATES:
        return (
            False,
            "Inbound contribution excluded because shipment condition is degraded.",
            freshness,
        )
    if freshness in {"stale", "critical", "unknown"}:
        return (
            False,
            "Inbound contribution excluded from trusted cover due to weak visibility.",
            freshness,
        )
    if shipment.eta_confidence is not None and shipment.eta_confidence < Decimal("0.60"):
        return False, "Low confidence inbound creates weak visibility for trusted cover.", freshness
    return True, None, freshness


def shipment_freshness(shipment: Shipment, evaluated_at: datetime) -> str:
    tracked_at = (
        shipment.last_tracking_update_at or shipment.latest_update_at or shipment.updated_at
    )
    result = classify_event_freshness(
        occurred_at=tracked_at,
        detected_at=evaluated_at,
        source_type=tracking_source_type_for(shipment),
    )
    return result.status.value


def tracking_source_type_for(shipment: Shipment) -> OperationalEventSourceType:
    if shipment.imo_number or shipment.mmsi or shipment.vessel_name:
        return OperationalEventSourceType.AIS
    return OperationalEventSourceType.MANUAL_UPLOAD


def implied_blocked_quantity(snapshot: StockSnapshot) -> Decimal:
    implied = snapshot.on_hand_mt - snapshot.quality_held_mt - snapshot.available_to_consume_mt
    return max(implied, Decimal("0"))


def quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
