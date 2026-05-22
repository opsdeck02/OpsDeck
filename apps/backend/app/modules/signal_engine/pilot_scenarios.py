from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, OperationalEvent, Plant, Shipment, StockSnapshot
from app.models.enums import (
    OperationalEventCategory,
    OperationalEventSourceType,
    OperationalEventType,
    ShipmentState,
)
from app.modules.operational_events.schemas import OperationalEventCreate
from app.modules.operational_events.service import create_operational_event
from app.schemas.context import RequestContext

SUPPORTED_PILOT_SCENARIOS = {
    "ocean_vessel_delay",
    "inland_movement_failure",
    "false_safety",
    "fresh_verified_inbound",
    "multi_inbound_mixed_protection",
}

PILOT_SCENARIO_LABELS = {
    "ocean_vessel_delay": "Ocean vessel delay",
    "inland_movement_failure": "Inland movement failure",
    "false_safety": "False safety: inbound exists but weak trust",
    "fresh_verified_inbound": "Fresh verified inbound",
    "multi_inbound_mixed_protection": "Multi-inbound mixed protection",
}

DEMO_DATA_NOTICE = "Pilot demo scenario - seeded demo data, not live customer operations."


@dataclass(frozen=True)
class PilotScenarioSelection:
    risk_type: str | None = None
    plant_reference: str | None = None
    material_reference: str | None = None
    shipment_reference: str | None = None
    severity: str | None = None
    scenario_key: str | None = None
    scenario_label: str | None = None


def prepare_pilot_scenario(
    db: Session,
    context: RequestContext,
    scenario: str,
    *,
    now: datetime | None = None,
) -> PilotScenarioSelection:
    if scenario not in SUPPORTED_PILOT_SCENARIOS:
        raise ValueError(f"Unsupported pilot scenario: {scenario}")

    scenario_now = now or datetime.now(UTC)
    if scenario == "ocean_vessel_delay":
        return seed_ocean_vessel_delay(db, context, scenario_now, scenario)
    if scenario == "inland_movement_failure":
        return seed_inland_movement_failure(db, context, scenario_now, scenario)
    if scenario == "false_safety":
        return seed_false_safety(db, context, scenario_now, scenario)
    if scenario == "fresh_verified_inbound":
        return seed_fresh_verified_inbound(db, context, scenario_now, scenario)
    return seed_multi_inbound_mixed_protection(db, context, scenario_now, scenario)


def seed_ocean_vessel_delay(
    db: Session,
    context: RequestContext,
    now: datetime,
    scenario_key: str,
) -> PilotScenarioSelection:
    plant, material = ensure_context(
        db,
        context,
        plant_code="DEMO-JAM-BF1",
        plant_name="Jamshedpur Blast Furnace 1",
        material_code="DEMO-COKING-COAL",
        material_name="Imported Coking Coal",
    )
    shipment = ensure_shipment(
        db,
        context,
        plant,
        material,
        shipment_id="DEMO-MV-EASTERN-LINE-01",
        current_eta=now + timedelta(days=4),
        planned_eta=now + timedelta(days=1),
        tracking_updated_at=now - timedelta(hours=40),
        quantity=Decimal("450"),
        vessel_name="MV Eastern Line",
        current_state=ShipmentState.IN_TRANSIT,
        current_milestone="on_water_eta_slipped",
        scenario_key=scenario_key,
    )
    ensure_stock(
        db,
        context,
        plant,
        material,
        on_hand=Decimal("20"),
        daily=Decimal("10"),
        now=now,
    )
    ensure_event(
        db,
        context,
        event_type=OperationalEventType.SHIPMENT_ETA_CHANGED,
        event_category=OperationalEventCategory.SHIPMENT,
        plant_reference=plant.code,
        material_reference=material.code,
        shipment_reference=shipment.shipment_id,
        occurred_at=now,
        scenario_key=scenario_key,
        previous_value={"current_eta": (now + timedelta(days=1)).isoformat()},
        new_value={"current_eta": (now + timedelta(days=4)).isoformat()},
    )
    db.commit()
    return PilotScenarioSelection(
        shipment_reference=shipment.shipment_id,
        severity="high",
        scenario_key=scenario_key,
        scenario_label=PILOT_SCENARIO_LABELS[scenario_key],
    )


def seed_inland_movement_failure(
    db: Session,
    context: RequestContext,
    now: datetime,
    scenario_key: str,
) -> PilotScenarioSelection:
    plant, material = ensure_context(
        db,
        context,
        plant_code="DEMO-KAL-RM2",
        plant_name="Kalinganagar Rolling Mill 2",
        material_code="DEMO-LIMESTONE",
        material_name="Limestone Flux",
    )
    shipment = ensure_shipment(
        db,
        context,
        plant,
        material,
        shipment_id="DEMO-INLAND-DHAMRA-TRUCK-17",
        current_eta=now + timedelta(days=5),
        planned_eta=now + timedelta(days=1),
        tracking_updated_at=now - timedelta(hours=30),
        quantity=Decimal("300"),
        vessel_name=None,
        current_state=ShipmentState.INLAND_TRANSIT,
        current_milestone="port_cleared inland_movement_not_confirmed",
        scenario_key=scenario_key,
    )
    ensure_stock(
        db,
        context,
        plant,
        material,
        on_hand=Decimal("25"),
        daily=Decimal("10"),
        now=now,
    )
    ensure_event(
        db,
        context,
        event_type=OperationalEventType.SHIPMENT_MILESTONE_UPDATED,
        event_category=OperationalEventCategory.SHIPMENT,
        plant_reference=plant.code,
        material_reference=material.code,
        shipment_reference=shipment.shipment_id,
        occurred_at=now,
        scenario_key=scenario_key,
        new_value={"current_milestone": "port_cleared inland_movement_not_confirmed"},
    )
    db.commit()
    return PilotScenarioSelection(
        shipment_reference=shipment.shipment_id,
        severity="high",
        scenario_key=scenario_key,
        scenario_label=PILOT_SCENARIO_LABELS[scenario_key],
    )


def seed_false_safety(
    db: Session,
    context: RequestContext,
    now: datetime,
    scenario_key: str,
) -> PilotScenarioSelection:
    plant, material = ensure_context(
        db,
        context,
        plant_code="DEMO-ANG-SMS",
        plant_name="Angul Steel Melting Shop",
        material_code="DEMO-FERRO-ALLOY",
        material_name="Ferro Alloy",
    )
    shipment = ensure_shipment(
        db,
        context,
        plant,
        material,
        shipment_id="DEMO-ERP-INBOUND-FA-900",
        current_eta=now + timedelta(days=3),
        planned_eta=now + timedelta(days=1),
        tracking_updated_at=now - timedelta(hours=36),
        quantity=Decimal("900"),
        vessel_name=None,
        current_state=ShipmentState.INLAND_TRANSIT,
        current_milestone="supplier_dispatch_unconfirmed",
        scenario_key=scenario_key,
    )
    ensure_stock(
        db,
        context,
        plant,
        material,
        on_hand=Decimal("15"),
        daily=Decimal("10"),
        now=now,
    )
    ensure_event(
        db,
        context,
        event_type=OperationalEventType.SHIPMENT_MILESTONE_UPDATED,
        event_category=OperationalEventCategory.SHIPMENT,
        plant_reference=plant.code,
        material_reference=material.code,
        shipment_reference=shipment.shipment_id,
        confidence_score=Decimal("35"),
        occurred_at=now,
        scenario_key=scenario_key,
        new_value={"current_milestone": "supplier_dispatch_unconfirmed"},
    )
    db.commit()
    return PilotScenarioSelection(
        plant_reference=plant.code,
        material_reference=material.code,
        scenario_key=scenario_key,
        scenario_label=PILOT_SCENARIO_LABELS[scenario_key],
    )


def seed_fresh_verified_inbound(
    db: Session,
    context: RequestContext,
    now: datetime,
    scenario_key: str,
) -> PilotScenarioSelection:
    plant, material = ensure_context(
        db,
        context,
        plant_code="DEMO-JSW-HSM",
        plant_name="Hot Strip Mill",
        material_code="DEMO-ZINC",
        material_name="Zinc Ingots",
    )
    shipment = ensure_shipment(
        db,
        context,
        plant,
        material,
        shipment_id="DEMO-VERIFIED-INBOUND-ZN-22",
        current_eta=now + timedelta(days=1),
        planned_eta=now + timedelta(days=1),
        tracking_updated_at=now - timedelta(minutes=20),
        quantity=Decimal("120"),
        vessel_name="MV Verified Coast",
        current_state=ShipmentState.IN_TRANSIT,
        current_milestone="verified_inbound_on_schedule",
        scenario_key=scenario_key,
    )
    ensure_stock(
        db,
        context,
        plant,
        material,
        on_hand=Decimal("40"),
        daily=Decimal("10"),
        now=now,
    )
    ensure_event(
        db,
        context,
        event_type=OperationalEventType.INVENTORY_STOCK_UPDATED,
        event_category=OperationalEventCategory.INVENTORY,
        plant_reference=plant.code,
        material_reference=material.code,
        shipment_reference=shipment.shipment_id,
        confidence_score=Decimal("95"),
        occurred_at=now,
        scenario_key=scenario_key,
        new_value={"verified_inbound": shipment.shipment_id},
    )
    db.commit()
    return PilotScenarioSelection(
        risk_type="days_of_cover_breach",
        plant_reference=plant.code,
        material_reference=material.code,
        scenario_key=scenario_key,
        scenario_label=PILOT_SCENARIO_LABELS[scenario_key],
    )


def seed_multi_inbound_mixed_protection(
    db: Session,
    context: RequestContext,
    now: datetime,
    scenario_key: str,
) -> PilotScenarioSelection:
    plant, material = ensure_context(
        db,
        context,
        plant_code="DEMO-TATA-BF2",
        plant_name="Blast Furnace 2",
        material_code="DEMO-PCI-COAL",
        material_name="PCI Coal",
    )
    ensure_stock(
        db,
        context,
        plant,
        material,
        on_hand=Decimal("20"),
        daily=Decimal("10"),
        now=now,
    )
    strong = ensure_shipment(
        db,
        context,
        plant,
        material,
        shipment_id="DEMO-MV-STRONG-PCI",
        current_eta=now + timedelta(days=1),
        planned_eta=now + timedelta(days=1),
        tracking_updated_at=now - timedelta(hours=1),
        quantity=Decimal("120"),
        vessel_name="MV Strong PCI",
        current_state=ShipmentState.IN_TRANSIT,
        current_milestone="verified_on_schedule",
        scenario_key=scenario_key,
    )
    weak = ensure_shipment(
        db,
        context,
        plant,
        material,
        shipment_id="DEMO-TRUCK-STALE-PCI",
        current_eta=now + timedelta(days=3),
        planned_eta=now + timedelta(days=1),
        tracking_updated_at=now - timedelta(hours=30),
        quantity=Decimal("200"),
        vessel_name=None,
        current_state=ShipmentState.INLAND_TRANSIT,
        current_milestone="truck_dispatch_stale",
        scenario_key=scenario_key,
    )
    late = ensure_shipment(
        db,
        context,
        plant,
        material,
        shipment_id="DEMO-MV-LATE-PCI",
        current_eta=now + timedelta(days=60),
        planned_eta=now + timedelta(days=1),
        tracking_updated_at=now - timedelta(hours=2),
        quantity=Decimal("400"),
        vessel_name="MV Late PCI",
        current_state=ShipmentState.IN_TRANSIT,
        current_milestone="late_ocean_inbound",
        scenario_key=scenario_key,
    )
    for shipment in (strong, weak, late):
        ensure_event(
            db,
            context,
            event_type=OperationalEventType.SHIPMENT_ETA_CHANGED,
            event_category=OperationalEventCategory.SHIPMENT,
            plant_reference=plant.code,
            material_reference=material.code,
            shipment_reference=shipment.shipment_id,
            occurred_at=now,
            scenario_key=scenario_key,
            new_value={"current_eta": shipment.current_eta.isoformat()},
        )
    db.commit()
    return PilotScenarioSelection(
        risk_type="days_of_cover_breach",
        plant_reference=plant.code,
        material_reference=material.code,
        scenario_key=scenario_key,
        scenario_label=PILOT_SCENARIO_LABELS[scenario_key],
    )


def ensure_context(
    db: Session,
    context: RequestContext,
    *,
    plant_code: str,
    plant_name: str,
    material_code: str,
    material_name: str,
) -> tuple[Plant, Material]:
    plant = db.scalar(
        select(Plant).where(
            Plant.tenant_id == context.tenant_id,
            Plant.code == plant_code,
        )
    )
    if plant is None:
        plant = Plant(
            tenant_id=context.tenant_id,
            code=plant_code,
            name=plant_name,
            location="India",
        )
        db.add(plant)
        db.flush()
    else:
        plant.name = plant_name

    material = db.scalar(
        select(Material).where(
            Material.tenant_id == context.tenant_id,
            Material.code == material_code,
        )
    )
    if material is None:
        material = Material(
            tenant_id=context.tenant_id,
            code=material_code,
            name=material_name,
            category="raw",
            uom="MT",
        )
        db.add(material)
        db.flush()
    else:
        material.name = material_name

    return plant, material


def ensure_stock(
    db: Session,
    context: RequestContext,
    plant: Plant,
    material: Material,
    *,
    on_hand: Decimal,
    daily: Decimal,
    now: datetime,
) -> None:
    snapshot = db.scalar(
        select(StockSnapshot)
        .where(
            StockSnapshot.tenant_id == context.tenant_id,
            StockSnapshot.plant_id == plant.id,
            StockSnapshot.material_id == material.id,
        )
        .order_by(StockSnapshot.snapshot_time.desc())
    )
    if snapshot is None:
        snapshot = StockSnapshot(
            tenant_id=context.tenant_id,
            plant_id=plant.id,
            material_id=material.id,
            on_hand_mt=on_hand,
            quality_held_mt=Decimal("0"),
            available_to_consume_mt=on_hand,
            daily_consumption_mt=daily,
            snapshot_time=now,
        )
        db.add(snapshot)
    else:
        snapshot.on_hand_mt = on_hand
        snapshot.quality_held_mt = Decimal("0")
        snapshot.available_to_consume_mt = on_hand
        snapshot.daily_consumption_mt = daily
        snapshot.snapshot_time = now


def ensure_shipment(
    db: Session,
    context: RequestContext,
    plant: Plant,
    material: Material,
    *,
    shipment_id: str,
    current_eta: datetime,
    planned_eta: datetime,
    tracking_updated_at: datetime,
    quantity: Decimal,
    vessel_name: str | None,
    current_state: ShipmentState,
    current_milestone: str,
    scenario_key: str,
) -> Shipment:
    shipment = db.scalar(
        select(Shipment).where(
            Shipment.tenant_id == context.tenant_id,
            Shipment.shipment_id == shipment_id,
        )
    )
    if shipment is None:
        shipment = Shipment(
            tenant_id=context.tenant_id,
            shipment_id=shipment_id,
            material_id=material.id,
            plant_id=plant.id,
            supplier_name="Pilot Demo Supplier",
            quantity_mt=quantity,
            vessel_name=vessel_name,
            imo_number="1234567" if vessel_name else None,
            mmsi="987654321" if vessel_name else None,
            planned_eta=planned_eta,
            current_eta=current_eta,
            latest_eta=planned_eta,
            current_milestone=current_milestone,
            last_tracking_update_at=tracking_updated_at,
            current_state=current_state,
            source_of_truth=f"pilot_scenario:{scenario_key}",
            latest_update_at=tracking_updated_at,
        )
        db.add(shipment)
        db.flush()
    else:
        shipment.material_id = material.id
        shipment.plant_id = plant.id
        shipment.supplier_name = "Pilot Demo Supplier"
        shipment.quantity_mt = quantity
        shipment.vessel_name = vessel_name
        shipment.imo_number = "1234567" if vessel_name else None
        shipment.mmsi = "987654321" if vessel_name else None
        shipment.planned_eta = planned_eta
        shipment.current_eta = current_eta
        shipment.latest_eta = planned_eta
        shipment.current_milestone = current_milestone
        shipment.last_tracking_update_at = tracking_updated_at
        shipment.current_state = current_state
        shipment.source_of_truth = f"pilot_scenario:{scenario_key}"
        shipment.latest_update_at = tracking_updated_at
    return shipment


def ensure_event(
    db: Session,
    context: RequestContext,
    *,
    event_type: OperationalEventType,
    event_category: OperationalEventCategory,
    plant_reference: str,
    material_reference: str,
    occurred_at: datetime,
    scenario_key: str,
    shipment_reference: str | None = None,
    confidence_score: Decimal | None = None,
    previous_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    metadata = pilot_metadata(scenario_key)
    marked_new_value = mark_payload(new_value, scenario_key)
    existing = db.scalar(
        select(OperationalEvent).where(
            OperationalEvent.tenant_id == context.tenant_id,
            OperationalEvent.event_type == event_type,
            OperationalEvent.plant_reference == plant_reference,
            OperationalEvent.material_reference == material_reference,
            OperationalEvent.shipment_reference == shipment_reference,
        )
    )
    if existing is not None:
        existing.occurred_at = occurred_at
        existing.detected_at = occurred_at
        existing.confidence_score = confidence_score
        existing.previous_value = previous_value
        existing.new_value = marked_new_value
        existing.metadata_json = {
            **(existing.metadata_json or {}),
            **metadata,
        }
        return

    create_operational_event(
        db,
        OperationalEventCreate(
            tenant_id=context.tenant_id,
            event_type=event_type,
            event_category=event_category,
            source_type=OperationalEventSourceType.MANUAL_UPLOAD,
            source_reference="pilot_scenario",
            occurred_at=occurred_at,
            detected_at=occurred_at,
            plant_reference=plant_reference,
            material_reference=material_reference,
            shipment_reference=shipment_reference,
            quantity_value=Decimal("20")
            if event_category == OperationalEventCategory.INVENTORY
            else None,
            quantity_unit="MT" if event_category == OperationalEventCategory.INVENTORY else None,
            previous_value=previous_value,
            new_value=marked_new_value,
            metadata=metadata,
            confidence_score=confidence_score,
        ),
    )


def pilot_metadata(scenario_key: str) -> dict[str, object]:
    return {
        "source": "pilot_scenario",
        "scenario_key": scenario_key,
        "demo_data": True,
        "created_for": "risk_workspace_pilot_demo",
    }


def mark_payload(value: dict | None, scenario_key: str) -> dict[str, object]:
    return {
        **(value or {}),
        "pilot_scenario": pilot_metadata(scenario_key),
    }
