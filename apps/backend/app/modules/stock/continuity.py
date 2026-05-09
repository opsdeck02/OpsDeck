from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, Plant, Shipment, StockSnapshot
from app.models.enums import ShipmentState
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
    now: datetime | None = None,
) -> InventoryContinuityResult:
    reserved = reserved_quantity or Decimal("0")
    blocked = blocked_quantity or Decimal("0")
    quality_hold = quality_hold_quantity or Decimal("0")
    inbound_committed = inbound_committed_quantity or Decimal("0")
    inbound_uncertain = inbound_uncertain_quantity or Decimal("0")
    usable_quantity = on_hand_quantity - reserved - blocked - quality_hold
    calculation_reasons = [
        (
            "Usable stock calculated from on-hand minus reserved, blocked, "
            "and quality-hold quantities"
        )
    ]

    days_of_cover: Decimal | None = None
    projected_exhaustion_date: datetime | None = None
    if daily_consumption_rate is None or daily_consumption_rate <= 0:
        calculation_reasons.append(
            "Days of cover is unknown because daily consumption rate is missing, zero, or negative"
        )
    else:
        days_of_cover = quantize_decimal(usable_quantity / daily_consumption_rate)
        calculation_reasons.append("Days of cover calculated using daily consumption rate")
        projected_exhaustion_date = ensure_utc(now or datetime.now(UTC)) + timedelta(
            days=float(days_of_cover)
        )
        calculation_reasons.append("Projected exhaustion date calculated from current time")

    if usable_quantity < 0:
        calculation_reasons.append("Usable stock is negative after inventory adjustments")

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
        daily_consumption_rate=(
            quantize_decimal(daily_consumption_rate)
            if daily_consumption_rate is not None
            else None
        ),
        days_of_cover=days_of_cover,
        projected_exhaustion_date=projected_exhaustion_date,
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


def implied_blocked_quantity(snapshot: StockSnapshot) -> Decimal:
    implied = snapshot.on_hand_mt - snapshot.quality_held_mt - snapshot.available_to_consume_mt
    return max(implied, Decimal("0"))


def quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
