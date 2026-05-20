from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, Plant, PlantMaterialThreshold, Shipment, StockSnapshot
from app.models.enums import ShipmentState
from app.modules.shipments.visibility_confidence import (
    calculate_visibility_confidence,
    is_physical_inbound_candidate,
)
from app.modules.shipments.visibility_confidence import (
    quantize_decimal as quantize_visibility_decimal,
)
from app.modules.stock.schemas import InventoryContinuityResult
from app.modules.suppliers.reliability_context import (
    calculate_supplier_reliability_context,
    supplier_reliability_modifier,
)
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
    physical_inbound_quantity_mt: Decimal | None = None,
    trusted_inbound_protection_mt: Decimal | None = None,
    visibility_uncertain_quantity_mt: Decimal | None = None,
    visibility_reason_chain: list[str] | None = None,
    threshold_days: Decimal | None = None,
    warning_days: Decimal | None = None,
    minimum_buffer_stock_days: Decimal | None = None,
    minimum_buffer_stock_mt: Decimal | None = None,
    stockout_alert_horizon_days: Decimal | None = None,
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
    physical_inbound = (
        physical_inbound_quantity_mt
        if physical_inbound_quantity_mt is not None
        else inbound_committed + inbound_uncertain
    )
    trusted_protection = (
        trusted_inbound_protection_mt
        if trusted_inbound_protection_mt is not None
        else trusted_inbound
    )
    visibility_uncertain = (
        visibility_uncertain_quantity_mt
        if visibility_uncertain_quantity_mt is not None
        else uncertain_inbound
    )
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
        physical_inbound_quantity_mt=quantize_decimal(physical_inbound),
        trusted_inbound_protection_mt=quantize_decimal(trusted_protection),
        visibility_uncertain_quantity_mt=quantize_decimal(visibility_uncertain),
        raw_days_of_cover=days_of_cover,
        threshold_days=quantize_decimal(threshold_days) if threshold_days is not None else None,
        warning_days=quantize_decimal(warning_days) if warning_days is not None else None,
        minimum_buffer_stock_days=(
            quantize_decimal(minimum_buffer_stock_days)
            if minimum_buffer_stock_days is not None
            else None
        ),
        minimum_buffer_stock_mt=(
            quantize_decimal(minimum_buffer_stock_mt)
            if minimum_buffer_stock_mt is not None
            else None
        ),
        stockout_alert_horizon_days=(
            quantize_decimal(stockout_alert_horizon_days)
            if stockout_alert_horizon_days is not None
            else None
        ),
        trusted_inbound_quantity=quantize_decimal(trusted_inbound),
        uncertain_inbound_quantity=quantize_decimal(uncertain_inbound),
        trusted_days_of_cover=trusted_days_of_cover,
        daily_consumption_rate=(
            quantize_decimal(daily_consumption_rate) if daily_consumption_rate is not None else None
        ),
        days_of_cover=days_of_cover,
        projected_exhaustion_date=projected_exhaustion_date,
        cover_confidence_score=quantize_decimal(cover_confidence_score),
        visibility_confidence=quantize_decimal(cover_confidence_score),
        freshness_status=freshness_status,
        trust_warnings=dedupe(warnings),
        visibility_reason_chain=dedupe(visibility_reason_chain or []),
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
    threshold = db.scalar(
        select(PlantMaterialThreshold).where(
            PlantMaterialThreshold.tenant_id == context.tenant_id,
            PlantMaterialThreshold.plant_id == plant_id,
            PlantMaterialThreshold.material_id == material_id,
        )
    )

    (
        trusted_inbound,
        uncertain_inbound,
        physical_inbound,
        freshness_status,
        trust_warnings,
        cover_confidence_score,
        visibility_reasons,
    ) = trusted_inbound_quantities(
        db,
        context.tenant_id,
        plant_id,
        material_id,
        now=now,
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
        physical_inbound_quantity_mt=physical_inbound,
        trusted_inbound_protection_mt=trusted_inbound,
        visibility_uncertain_quantity_mt=uncertain_inbound,
        visibility_reason_chain=visibility_reasons,
        threshold_days=threshold.threshold_days if threshold else None,
        warning_days=threshold.warning_days if threshold else None,
        minimum_buffer_stock_days=threshold.minimum_buffer_stock_days if threshold else None,
        minimum_buffer_stock_mt=threshold.minimum_buffer_stock_mt if threshold else None,
        stockout_alert_horizon_days=threshold.stockout_alert_horizon_days if threshold else None,
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
) -> tuple[Decimal, Decimal, Decimal, str, list[str], Decimal, list[str]]:
    evaluated_at = ensure_utc(now or datetime.now(UTC))
    trusted = Decimal("0")
    uncertain = Decimal("0")
    physical = Decimal("0")
    warnings: list[str] = []
    reason_chain: list[str] = []
    total_count = 0
    confidence_sum = Decimal("0")
    shipments = db.scalars(
        select(Shipment).where(
            Shipment.tenant_id == tenant_id,
            Shipment.plant_id == plant_id,
            Shipment.material_id == material_id,
        )
    )
    for shipment in shipments:
        if not is_physical_inbound_candidate(shipment):
            continue
        total_count += 1
        result = calculate_visibility_confidence(shipment, now=evaluated_at)
        reliability = calculate_supplier_reliability_context(
            db,
            tenant_id=tenant_id,
            shipment=shipment,
            visibility_result=result,
            now=evaluated_at,
        )
        modifier = supplier_reliability_modifier(reliability.reliability_band)
        adjusted_confidence = max(
            Decimal("0.00"),
            min(Decimal("1.00"), result.visibility_confidence + modifier),
        )
        trusted_protection = quantize_visibility_decimal(
            result.physical_inbound_quantity_mt * adjusted_confidence
        )
        visibility_uncertainty = quantize_visibility_decimal(
            result.physical_inbound_quantity_mt - trusted_protection
        )
        physical += result.physical_inbound_quantity_mt
        trusted += trusted_protection
        uncertain += visibility_uncertainty
        confidence_sum += adjusted_confidence
        reason_chain.extend(
            f"Shipment {shipment.shipment_id}: {reason}" for reason in result.reason_chain
        )
        reason_chain.extend(
            f"Shipment {shipment.shipment_id}: {reason}" for reason in reliability.reason_chain
        )
        if modifier:
            reason_chain.append(
                f"Shipment {shipment.shipment_id}: Supplier reliability band "
                f"{reliability.reliability_band} adjusted trusted inbound protection "
                f"confidence by {modifier}."
            )
        if visibility_uncertainty > 0:
            warnings.append(
                "Inbound protection includes visibility uncertainty; physical inbound quantity "
                "has not disappeared."
            )

    if total_count == 0:
        return Decimal("0"), Decimal("0"), Decimal("0"), "unknown", [], Decimal("1.00"), []
    confidence = confidence_sum / Decimal(str(total_count))
    if uncertain > 0:
        warnings.append(
            "Visibility uncertainty moved part of physical inbound quantity out of trusted "
            "inbound protection."
        )
    freshness = visibility_freshness_label(quantize_decimal(confidence))
    return (
        quantize_decimal(trusted),
        quantize_decimal(uncertain),
        quantize_decimal(physical),
        freshness,
        dedupe(warnings),
        quantize_decimal(confidence),
        dedupe(reason_chain),
    )


def visibility_freshness_label(confidence: Decimal) -> str:
    if confidence >= Decimal("0.80"):
        return "fresh"
    if confidence >= Decimal("0.60"):
        return "delayed"
    if confidence >= Decimal("0.40"):
        return "stale"
    return "critical"


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
