from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Material, Plant, Shipment, StockSnapshot, Tenant
from app.models.enums import ShipmentState
from app.modules.stock.continuity import (
    calculate_inventory_continuity,
    calculate_inventory_continuity_for,
)
from app.schemas.context import RequestContext


def test_usable_stock_calculation() -> None:
    result = calculate_inventory_continuity(
        plant_reference="P1",
        material_reference="M1",
        on_hand_quantity=Decimal("100"),
        reserved_quantity=Decimal("10"),
        blocked_quantity=Decimal("5"),
        quality_hold_quantity=Decimal("2"),
        daily_consumption_rate=Decimal("10"),
        unit="MT",
        now=datetime(2026, 5, 9, tzinfo=UTC),
    )

    assert result.usable_quantity == Decimal("83.00")


def test_days_of_cover_calculation() -> None:
    result = calculate_inventory_continuity(
        plant_reference="P1",
        material_reference="M1",
        on_hand_quantity=Decimal("85"),
        daily_consumption_rate=Decimal("12"),
        unit="MT",
        now=datetime(2026, 5, 9, tzinfo=UTC),
    )

    assert result.days_of_cover == Decimal("7.08")
    assert result.raw_days_of_cover == Decimal("7.08")
    assert result.trusted_days_of_cover == Decimal("7.08")


def test_projected_exhaustion_date_calculation() -> None:
    now = datetime(2026, 5, 9, 6, tzinfo=UTC)
    result = calculate_inventory_continuity(
        plant_reference="P1",
        material_reference="M1",
        on_hand_quantity=Decimal("48"),
        daily_consumption_rate=Decimal("24"),
        unit="MT",
        now=now,
    )

    assert result.projected_exhaustion_date == datetime(2026, 5, 11, 6, tzinfo=UTC)


def test_missing_consumption_rate_returns_unknown_days_of_cover() -> None:
    result = calculate_inventory_continuity(
        plant_reference="P1",
        material_reference="M1",
        on_hand_quantity=Decimal("100"),
        daily_consumption_rate=None,
        unit="MT",
        now=datetime(2026, 5, 9, tzinfo=UTC),
    )

    assert result.days_of_cover is None
    assert result.trusted_days_of_cover is None
    assert result.projected_exhaustion_date is None
    assert "consumption rate is missing" in result.trust_warnings[0]


def test_zero_and_negative_consumption_rate_do_not_crash() -> None:
    zero = calculate_inventory_continuity(
        plant_reference="P1",
        material_reference="M1",
        on_hand_quantity=Decimal("100"),
        daily_consumption_rate=Decimal("0"),
        unit="MT",
    )
    negative = calculate_inventory_continuity(
        plant_reference="P1",
        material_reference="M1",
        on_hand_quantity=Decimal("100"),
        daily_consumption_rate=Decimal("-5"),
        unit="MT",
    )

    assert zero.days_of_cover is None
    assert negative.days_of_cover is None


def test_reserved_blocked_and_quality_hold_reduce_usable_stock() -> None:
    result = calculate_inventory_continuity(
        plant_reference="P1",
        material_reference="M1",
        on_hand_quantity=Decimal("100"),
        reserved_quantity=Decimal("20"),
        blocked_quantity=Decimal("30"),
        quality_hold_quantity=Decimal("60"),
        daily_consumption_rate=Decimal("10"),
        unit="MT",
    )

    assert result.usable_quantity == Decimal("-10.00")
    assert "Usable stock is negative" in result.calculation_reasons[-1]


def test_inventory_continuity_preserves_tenant_isolation() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            tenant_a, tenant_b = seed_inventory_continuity_data(db)
            result_a = calculate_inventory_continuity_for(
                db,
                RequestContext(
                    tenant_id=tenant_a.id,
                    tenant_slug=tenant_a.slug,
                    role="tenant_admin",
                    user_id=1,
                ),
                1,
                1,
                now=datetime(2026, 5, 9, tzinfo=UTC),
            )
            result_b = calculate_inventory_continuity_for(
                db,
                RequestContext(
                    tenant_id=tenant_b.id,
                    tenant_slug=tenant_b.slug,
                    role="tenant_admin",
                    user_id=1,
                ),
                1,
                1,
                now=datetime(2026, 5, 9, tzinfo=UTC),
            )

            assert result_a is not None
            assert result_a.plant_reference == "P1"
            assert result_a.usable_quantity == Decimal("80.00")
            assert result_a.inbound_committed_quantity == Decimal("50.00")
            assert result_a.inbound_uncertain_quantity == Decimal("25.00")
            assert result_a.physical_inbound_quantity_mt == Decimal("75.00")
            assert result_a.trusted_inbound_quantity == Decimal("45.00")
            assert result_a.uncertain_inbound_quantity == Decimal("30.00")
            assert result_a.trusted_days_of_cover == Decimal("6.25")
            assert result_b is None
    finally:
        Base.metadata.drop_all(bind=engine)


def test_trusted_inbound_increases_trusted_cover() -> None:
    with inventory_test_session() as db:
        tenant, plant, material = seed_single_inventory_context(db)
        db.add(
            Shipment(
                tenant_id=tenant.id,
                shipment_id="TRUSTED-IN",
                material_id=material.id,
                plant_id=plant.id,
                supplier_name="Supplier A",
                quantity_mt=Decimal("40"),
                planned_eta=datetime(2026, 5, 10, tzinfo=UTC),
                current_eta=datetime(2026, 5, 10, tzinfo=UTC),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="manual_upload",
                latest_update_at=datetime(2026, 5, 9, 10, tzinfo=UTC),
                eta_confidence=Decimal("0.90"),
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
            now=datetime(2026, 5, 9, 12, tzinfo=UTC),
        )

        assert result is not None
        assert result.days_of_cover == Decimal("4.00")
        assert result.physical_inbound_quantity_mt == Decimal("40.00")
        assert result.trusted_inbound_quantity == Decimal("24.00")
        assert result.uncertain_inbound_quantity == Decimal("16.00")
        assert result.trusted_days_of_cover == Decimal("5.20")
        assert result.projected_exhaustion_date == datetime(2026, 5, 14, 16, 48, tzinfo=UTC)


def test_degraded_or_stale_inbound_is_uncertain() -> None:
    with inventory_test_session() as db:
        tenant, plant, material = seed_single_inventory_context(db)
        db.add_all(
            [
                Shipment(
                    tenant_id=tenant.id,
                    shipment_id="DEGRADED-IN",
                    material_id=material.id,
                    plant_id=plant.id,
                    supplier_name="Supplier A",
                    quantity_mt=Decimal("30"),
                    planned_eta=datetime(2026, 5, 10, tzinfo=UTC),
                    current_eta=datetime(2026, 5, 13, tzinfo=UTC),
                    current_state=ShipmentState.DELAYED,
                    source_of_truth="manual_upload",
                    latest_update_at=datetime(2026, 5, 9, 10, tzinfo=UTC),
                ),
                Shipment(
                    tenant_id=tenant.id,
                    shipment_id="STALE-IN",
                    material_id=material.id,
                    plant_id=plant.id,
                    supplier_name="Supplier A",
                    quantity_mt=Decimal("20"),
                    planned_eta=datetime(2026, 5, 10, tzinfo=UTC),
                    current_eta=datetime(2026, 5, 10, tzinfo=UTC),
                    current_state=ShipmentState.IN_TRANSIT,
                    source_of_truth="manual_upload",
                    latest_update_at=datetime(2026, 5, 1, tzinfo=UTC),
                ),
            ]
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
            now=datetime(2026, 5, 9, 12, tzinfo=UTC),
        )

        assert result is not None
        assert result.physical_inbound_quantity_mt == Decimal("50.00")
        assert result.trusted_inbound_quantity == Decimal("6.50")
        assert result.uncertain_inbound_quantity == Decimal("43.50")
        assert result.trusted_days_of_cover == Decimal("4.33")
        assert any("Visibility uncertainty" in warning for warning in result.trust_warnings)


def test_low_confidence_inbound_creates_trust_warning() -> None:
    with inventory_test_session() as db:
        tenant, plant, material = seed_single_inventory_context(db)
        db.add(
            Shipment(
                tenant_id=tenant.id,
                shipment_id="LOW-CONF-IN",
                material_id=material.id,
                plant_id=plant.id,
                supplier_name="Supplier A",
                quantity_mt=Decimal("30"),
                planned_eta=datetime(2026, 5, 10, tzinfo=UTC),
                current_eta=datetime(2026, 5, 10, tzinfo=UTC),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="manual_upload",
                latest_update_at=datetime(2026, 5, 9, 10, tzinfo=UTC),
                eta_confidence=Decimal("0.40"),
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
            now=datetime(2026, 5, 9, 12, tzinfo=UTC),
        )

        assert result is not None
        assert result.physical_inbound_quantity_mt == Decimal("30.00")
        assert result.trusted_inbound_quantity == Decimal("18.00")
        assert result.uncertain_inbound_quantity == Decimal("12.00")
        assert any("Visibility uncertainty" in warning for warning in result.trust_warnings)


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


def seed_single_inventory_context(db: Session) -> tuple[Tenant, Plant, Material]:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    db.add(tenant)
    db.flush()
    plant = Plant(tenant_id=tenant.id, code="P1", name="Plant 1", location=None)
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
            on_hand_mt=Decimal("100"),
            quality_held_mt=Decimal("10"),
            available_to_consume_mt=Decimal("80"),
            daily_consumption_mt=Decimal("20"),
            snapshot_time=datetime(2026, 5, 9, tzinfo=UTC),
        )
    )
    db.commit()
    return tenant, plant, material


def seed_inventory_continuity_data(db: Session) -> tuple[Tenant, Tenant]:
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    db.add_all([tenant_a, tenant_b])
    db.flush()

    plant_a = Plant(tenant_id=tenant_a.id, code="P1", name="Plant 1", location=None)
    material_a = Material(
        tenant_id=tenant_a.id,
        code="M1",
        name="Material 1",
        category="raw",
        uom="MT",
    )
    plant_b = Plant(tenant_id=tenant_b.id, code="P1", name="Other Plant", location=None)
    material_b = Material(
        tenant_id=tenant_b.id,
        code="M1",
        name="Other Material",
        category="raw",
        uom="MT",
    )
    db.add_all([plant_a, material_a, plant_b, material_b])
    db.flush()

    db.add(
        StockSnapshot(
            tenant_id=tenant_a.id,
            plant_id=plant_a.id,
            material_id=material_a.id,
            on_hand_mt=Decimal("100"),
            quality_held_mt=Decimal("10"),
            available_to_consume_mt=Decimal("80"),
            daily_consumption_mt=Decimal("20"),
            snapshot_time=datetime(2026, 5, 9, tzinfo=UTC),
        )
    )
    db.add(
        StockSnapshot(
            tenant_id=tenant_b.id,
            plant_id=plant_b.id,
            material_id=material_b.id,
            on_hand_mt=Decimal("999"),
            quality_held_mt=Decimal("0"),
            available_to_consume_mt=Decimal("999"),
            daily_consumption_mt=Decimal("1"),
            snapshot_time=datetime(2026, 5, 9, tzinfo=UTC),
        )
    )
    db.add(
        Shipment(
            tenant_id=tenant_a.id,
            shipment_id="A-COMMITTED",
            material_id=material_a.id,
            plant_id=plant_a.id,
            supplier_name="Supplier A",
            quantity_mt=Decimal("50"),
            planned_eta=datetime(2026, 5, 10, tzinfo=UTC),
            current_eta=datetime(2026, 5, 10, tzinfo=UTC),
            current_state=ShipmentState.IN_TRANSIT,
            source_of_truth="manual_upload",
            latest_update_at=datetime(2026, 5, 9, tzinfo=UTC),
        )
    )
    db.add(
        Shipment(
            tenant_id=tenant_a.id,
            shipment_id="A-UNCERTAIN",
            material_id=material_a.id,
            plant_id=plant_a.id,
            supplier_name="Supplier A",
            quantity_mt=Decimal("25"),
            planned_eta=datetime(2026, 5, 11, tzinfo=UTC),
            current_eta=datetime(2026, 5, 11, tzinfo=UTC),
            current_state=ShipmentState.PLANNED,
            source_of_truth="manual_upload",
            latest_update_at=datetime(2026, 5, 9, tzinfo=UTC),
        )
    )
    db.commit()
    return tenant_a, tenant_b
