from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Material, Plant, Shipment, StockSnapshot, Tenant
from app.models.enums import ShipmentState
from app.modules.shipments.visibility_confidence import calculate_visibility_confidence
from app.modules.stock.continuity import calculate_inventory_continuity_for
from app.schemas.context import RequestContext

NOW = datetime(2026, 5, 20, 12, tzinfo=UTC)


def test_ocean_stable_eta_with_48h_no_update_keeps_high_confidence() -> None:
    result = calculate_visibility_confidence(
        shipment(
            vessel_name="MV Stable",
            current_state=ShipmentState.IN_TRANSIT,
            latest_update_at=NOW - timedelta(hours=48),
        ),
        now=NOW,
    )

    assert result.visibility_profile == "ocean"
    assert result.expected_visibility_cadence_hours == Decimal("72")
    assert result.eta_stability_status == "stable"
    assert result.visibility_confidence == Decimal("0.90")
    assert result.trusted_inbound_protection_mt == Decimal("90.00")
    assert result.physical_inbound_quantity_mt == Decimal("100.00")


def test_inland_24h_no_update_degrades_confidence() -> None:
    result = calculate_visibility_confidence(
        shipment(
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
            latest_update_at=NOW - timedelta(hours=24),
        ),
        now=NOW,
    )

    assert result.visibility_profile == "inland"
    assert result.expected_visibility_cadence_hours == Decimal("6")
    assert result.visibility_confidence < Decimal("0.50")
    assert result.visibility_uncertain_quantity_mt > Decimal("50.00")


def test_eta_degraded_reduces_confidence() -> None:
    stable = calculate_visibility_confidence(shipment(), now=NOW)
    degraded = calculate_visibility_confidence(
        shipment(current_eta=NOW + timedelta(days=4), planned_eta=NOW + timedelta(days=1)),
        now=NOW,
    )

    assert degraded.eta_stability_status == "degraded"
    assert degraded.visibility_confidence == stable.visibility_confidence - Decimal("0.25")


def test_ocean_12h_eta_drift_remains_stable_high_confidence() -> None:
    result = calculate_visibility_confidence(
        shipment(
            vessel_name="MV Tolerant",
            planned_eta=NOW + timedelta(days=5),
            current_eta=NOW + timedelta(days=5, hours=12),
        ),
        now=NOW,
    )

    assert result.visibility_profile == "ocean"
    assert result.eta_context_tolerance_profile == "tolerant"
    assert result.eta_behavior_status == "stable"
    assert result.visibility_confidence == Decimal("0.90")
    assert any("tolerant ETA expectations" in reason for reason in result.reason_chain)


def test_inland_12h_eta_drift_degrades_confidence() -> None:
    result = calculate_visibility_confidence(
        shipment(
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
            planned_eta=NOW + timedelta(days=1),
            current_eta=NOW + timedelta(days=1, hours=12),
        ),
        now=NOW,
    )

    assert result.visibility_profile == "inland"
    assert result.eta_context_tolerance_profile == "strict"
    assert result.eta_behavior_status == "degraded"
    assert result.visibility_confidence == Decimal("0.50")


def test_near_destination_uses_very_strict_eta_tolerance() -> None:
    result = calculate_visibility_confidence(
        shipment(
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="near_plant gate_in",
            planned_eta=NOW + timedelta(hours=6),
            current_eta=NOW + timedelta(hours=9),
        ),
        now=NOW,
    )

    assert result.eta_context_tolerance_profile == "very_strict"
    assert result.eta_drift_tolerance_hours == Decimal("2")
    assert result.eta_behavior_status == "drifting"


def test_repeated_eta_drift_has_larger_penalty_than_one_time_drift() -> None:
    one_time = calculate_visibility_confidence(
        shipment(
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
            planned_eta=NOW + timedelta(days=1),
            current_eta=NOW + timedelta(days=1, hours=8),
        ),
        now=NOW,
    )
    repeated = calculate_visibility_confidence(
        shipment(
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
            delay_status="watch",
            planned_eta=NOW + timedelta(days=1),
            latest_eta=NOW + timedelta(days=1, hours=6),
            current_eta=NOW + timedelta(days=1, hours=8),
        ),
        now=NOW,
    )

    assert one_time.eta_behavior_status == "drifting"
    assert repeated.eta_behavior_status == "repeatedly_drifting"
    assert repeated.eta_confidence_penalty < one_time.eta_confidence_penalty
    assert repeated.visibility_confidence < one_time.visibility_confidence


def test_recovering_eta_restores_partial_confidence() -> None:
    stable = calculate_visibility_confidence(
        shipment(
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
        ),
        now=NOW,
    )
    recovering = calculate_visibility_confidence(
        shipment(
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
            planned_eta=NOW + timedelta(days=1),
            latest_eta=NOW + timedelta(days=1, hours=12),
            current_eta=NOW + timedelta(days=1, hours=2),
        ),
        now=NOW,
    )

    assert recovering.eta_behavior_status == "recovering"
    assert recovering.visibility_confidence == stable.visibility_confidence + Decimal("0.05")
    assert any("partially restored" in reason for reason in recovering.reason_chain)


def test_volatile_eta_conditions_reduce_confidence_heavily() -> None:
    result = calculate_visibility_confidence(
        shipment(
            current_state=ShipmentState.DELAYED,
            current_milestone="truck delayed exception",
            planned_eta=NOW + timedelta(days=1),
            current_eta=NOW + timedelta(days=1, hours=20),
            latest_update_at=NOW - timedelta(hours=20),
        ),
        now=NOW,
    )

    assert result.eta_behavior_status == "volatile"
    assert result.visibility_confidence <= Decimal("0.10")
    assert any("ETA volatility detected" in reason for reason in result.reason_chain)


def test_abnormal_delayed_state_reduces_confidence() -> None:
    result = calculate_visibility_confidence(
        shipment(current_state=ShipmentState.DELAYED),
        now=NOW,
    )

    assert result.abnormal_visibility_behavior is True
    assert result.visibility_confidence <= Decimal("0.30")
    assert any("Abnormal shipment state" in reason for reason in result.reason_chain)


def test_physical_trusted_and_uncertain_quantities_are_separated() -> None:
    result = calculate_visibility_confidence(
        shipment(
            current_state=ShipmentState.INLAND_TRANSIT,
            latest_update_at=NOW - timedelta(hours=24),
        ),
        now=NOW,
    )

    assert result.physical_inbound_quantity_mt == Decimal("100.00")
    assert result.trusted_inbound_protection_mt < result.physical_inbound_quantity_mt
    assert (
        result.visibility_uncertain_quantity_mt
        == result.physical_inbound_quantity_mt - result.trusted_inbound_protection_mt
    )


def test_inventory_continuity_uses_trusted_inbound_protection_for_cover() -> None:
    with inventory_test_session() as db:
        tenant, plant, material = seed_inventory_context(db)
        db.add(
            shipment(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                shipment_id="INLAND-STALE",
                current_state=ShipmentState.INLAND_TRANSIT,
                current_milestone="truck dispatched",
                latest_update_at=NOW - timedelta(hours=24),
                quantity_mt=Decimal("100"),
            )
        )
        db.commit()

        result = calculate_inventory_continuity_for(
            db,
            RequestContext(
                tenant_id=tenant.id,
                tenant_slug=tenant.slug,
                role="tenant_admin",
                user_id=1,
            ),
            plant.id,
            material.id,
            now=NOW,
        )

        assert result is not None
        assert result.physical_inbound_quantity_mt == Decimal("100.00")
        assert result.trusted_inbound_quantity == Decimal("40.00")
        assert result.uncertain_inbound_quantity == Decimal("60.00")
        assert result.trusted_days_of_cover == Decimal("9.00")
        assert result.visibility_reason_chain


def test_missing_data_falls_back_to_unknown_profile_without_crashing() -> None:
    result = calculate_visibility_confidence(
        shipment(current_eta=None, planned_eta=None, latest_update_at=None),
        now=NOW,
    )

    assert result.visibility_profile == "unknown"
    assert result.eta_stability_status == "unknown"
    assert result.eta_behavior_status == "unknown"
    assert result.visibility_confidence == Decimal("0.30")
    assert any("No shipment update timestamp" in reason for reason in result.reason_chain)


def test_visibility_confidence_clamps_at_zero() -> None:
    result = calculate_visibility_confidence(
        shipment(
            current_state=ShipmentState.CANCELLED,
            current_milestone="blocked hold exception",
            delay_status="delayed",
            planned_eta=NOW + timedelta(days=1),
            latest_eta=NOW + timedelta(days=2),
            current_eta=NOW + timedelta(days=5),
            latest_update_at=NOW - timedelta(days=10),
        ),
        now=NOW,
    )

    assert result.visibility_confidence == Decimal("0.00")
    assert result.trusted_inbound_protection_mt == Decimal("0.00")
    assert result.visibility_uncertain_quantity_mt == Decimal("100.00")


def shipment(**overrides) -> Shipment:
    values = {
        "tenant_id": 1,
        "shipment_id": "SHIP-1",
        "material_id": 1,
        "plant_id": 1,
        "supplier_name": "Supplier",
        "quantity_mt": Decimal("100"),
        "planned_eta": NOW + timedelta(days=2),
        "current_eta": NOW + timedelta(days=2),
        "latest_eta": None,
        "current_state": ShipmentState.IN_TRANSIT,
        "current_milestone": "in_transit",
        "source_of_truth": "manual_upload",
        "latest_update_at": NOW - timedelta(hours=2),
    }
    values.update(overrides)
    return Shipment(**values)


def inventory_test_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    class ManagedSession:
        def __enter__(self) -> Session:
            self.db = SessionLocal()
            return self.db

        def __exit__(self, exc_type, exc, tb) -> None:
            self.db.close()
            Base.metadata.drop_all(bind=engine)

    return ManagedSession()


def seed_inventory_context(db: Session) -> tuple[Tenant, Plant, Material]:
    tenant = Tenant(name="Tenant", slug="tenant")
    db.add(tenant)
    db.flush()
    plant = Plant(tenant_id=tenant.id, code="P1", name="Plant 1", location="India")
    material = Material(
        tenant_id=tenant.id,
        code="M1",
        name="Material 1",
        category="raw",
        uom="MT",
    )
    db.add_all([plant, material])
    db.flush()
    db.add(
        StockSnapshot(
            tenant_id=tenant.id,
            plant_id=plant.id,
            material_id=material.id,
            on_hand_mt=Decimal("50"),
            quality_held_mt=Decimal("0"),
            available_to_consume_mt=Decimal("50"),
            daily_consumption_mt=Decimal("10"),
            snapshot_time=NOW,
        )
    )
    db.flush()
    return tenant, plant, material
