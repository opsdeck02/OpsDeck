from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Material, Plant, Shipment, Tenant
from app.models.enums import OperationalEventSourceType, ShipmentState
from app.modules.shipments.continuity import (
    calculate_shipment_continuity,
    calculate_shipment_continuity_for,
)
from app.schemas.context import RequestContext


def test_shipment_with_no_delay_returns_on_track() -> None:
    now = datetime(2026, 5, 9, 12, tzinfo=UTC)
    result = continuity_result(
        eta=now + timedelta(days=2),
        previous_eta=now + timedelta(days=2),
        now=now,
    )

    assert result.status == "on_track"
    assert result.eta_slip_days == Decimal("0.00")


def test_shipment_with_small_eta_slip_returns_watch() -> None:
    now = datetime(2026, 5, 9, 12, tzinfo=UTC)
    result = continuity_result(
        eta=now + timedelta(days=2, hours=12),
        previous_eta=now + timedelta(days=2),
        now=now,
    )

    assert result.status == "watch"
    assert result.eta_slip_days == Decimal("0.50")


def test_shipment_with_large_eta_slip_returns_degraded() -> None:
    now = datetime(2026, 5, 9, 12, tzinfo=UTC)
    result = continuity_result(
        eta=now + timedelta(days=4),
        previous_eta=now + timedelta(days=2),
        now=now,
    )

    assert result.status == "degraded"
    assert result.eta_slip_days == Decimal("2.00")


def test_stale_tracking_freshness_returns_degraded() -> None:
    now = datetime(2026, 5, 9, 12, tzinfo=UTC)
    result = continuity_result(
        eta=now + timedelta(days=2),
        previous_eta=now + timedelta(days=2),
        tracking_updated_at=now - timedelta(hours=8),
        tracking_source_type=OperationalEventSourceType.AIS,
        now=now,
    )

    assert result.status == "degraded"
    assert result.tracking_freshness_status == "stale"


def test_missing_eta_returns_unknown() -> None:
    now = datetime(2026, 5, 9, 12, tzinfo=UTC)
    result = continuity_result(eta=None, previous_eta=now + timedelta(days=2), now=now)

    assert result.status == "unknown"
    assert "Current ETA is missing" in result.continuity_reasons


def test_missing_linked_context_returns_watch_if_otherwise_on_track() -> None:
    now = datetime(2026, 5, 9, 12, tzinfo=UTC)
    result = continuity_result(
        eta=now + timedelta(days=2),
        previous_eta=now + timedelta(days=2),
        linked_purchase_order_reference=None,
        linked_material_reference=None,
        linked_plant_reference=None,
        now=now,
    )

    assert result.status == "watch"
    assert "Missing linked context" in result.continuity_reasons[-1]


def test_continuity_reasons_are_generated() -> None:
    now = datetime(2026, 5, 9, 12, tzinfo=UTC)
    result = continuity_result(
        eta=now + timedelta(days=3),
        previous_eta=now + timedelta(days=1),
        tracking_updated_at=now - timedelta(hours=8),
        now=now,
    )

    assert any("ETA slipped" in reason for reason in result.continuity_reasons)
    assert any("Tracking data is" in reason for reason in result.continuity_reasons)


def test_shipment_continuity_preserves_tenant_isolation() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            tenant_a, tenant_b = seed_shipment_continuity_data(db)
            result_a = calculate_shipment_continuity_for(
                db,
                RequestContext(
                    tenant_id=tenant_a.id,
                    tenant_slug=tenant_a.slug,
                    role="tenant_admin",
                    user_id=1,
                ),
                "SHIP-A",
                now=datetime(2026, 5, 9, 12, tzinfo=UTC),
            )
            result_b = calculate_shipment_continuity_for(
                db,
                RequestContext(
                    tenant_id=tenant_b.id,
                    tenant_slug=tenant_b.slug,
                    role="tenant_admin",
                    user_id=1,
                ),
                "SHIP-A",
                now=datetime(2026, 5, 9, 12, tzinfo=UTC),
            )

            assert result_a is not None
            assert result_a.linked_plant_reference == "P1"
            assert result_a.linked_material_reference == "M1"
            assert result_b is None
    finally:
        Base.metadata.drop_all(bind=engine)


def continuity_result(
    *,
    eta: datetime | None,
    previous_eta: datetime | None,
    now: datetime,
    current_milestone: str | None = "in_transit",
    tracking_updated_at: datetime | None = None,
    tracking_source_type: OperationalEventSourceType = OperationalEventSourceType.AIS,
    linked_purchase_order_reference: str | None = "PO-1",
    linked_material_reference: str | None = "M1",
    linked_plant_reference: str | None = "P1",
):
    return calculate_shipment_continuity(
        shipment_reference="SHIP-1",
        eta=eta,
        previous_eta=previous_eta,
        current_milestone=current_milestone,
        tracking_updated_at=tracking_updated_at or now - timedelta(minutes=30),
        tracking_source_type=tracking_source_type,
        linked_purchase_order_reference=linked_purchase_order_reference,
        linked_material_reference=linked_material_reference,
        linked_plant_reference=linked_plant_reference,
        current_state=ShipmentState.IN_TRANSIT,
        now=now,
    )


def seed_shipment_continuity_data(db: Session) -> tuple[Tenant, Tenant]:
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
    plant_b = Plant(tenant_id=tenant_b.id, code="P2", name="Plant 2", location=None)
    material_b = Material(
        tenant_id=tenant_b.id,
        code="M2",
        name="Material 2",
        category="raw",
        uom="MT",
    )
    db.add_all([plant_a, material_a, plant_b, material_b])
    db.flush()

    now = datetime(2026, 5, 9, 12, tzinfo=UTC)
    db.add(
        Shipment(
            tenant_id=tenant_a.id,
            shipment_id="SHIP-A",
            material_id=material_a.id,
            plant_id=plant_a.id,
            supplier_name="Supplier A",
            quantity_mt=Decimal("100"),
            planned_eta=now + timedelta(days=2),
            current_eta=now + timedelta(days=2),
            current_milestone="in_transit",
            last_tracking_update_at=now - timedelta(minutes=30),
            current_state=ShipmentState.IN_TRANSIT,
            source_of_truth="manual_upload",
            latest_update_at=now - timedelta(minutes=30),
        )
    )
    db.add(
        Shipment(
            tenant_id=tenant_b.id,
            shipment_id="SHIP-B",
            material_id=material_b.id,
            plant_id=plant_b.id,
            supplier_name="Supplier B",
            quantity_mt=Decimal("100"),
            planned_eta=now + timedelta(days=2),
            current_eta=now + timedelta(days=2),
            current_milestone="in_transit",
            last_tracking_update_at=now - timedelta(minutes=30),
            current_state=ShipmentState.IN_TRANSIT,
            source_of_truth="manual_upload",
            latest_update_at=now - timedelta(minutes=30),
        )
    )
    db.commit()
    return tenant_a, tenant_b
