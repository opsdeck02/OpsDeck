from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Material, Plant, Shipment, StockSnapshot, Tenant
from app.models.enums import (
    OperationalEventCategory,
    OperationalEventFreshnessStatus,
    OperationalEventSourceType,
    OperationalEventType,
    ShipmentState,
)
from app.modules.exposure.mapping import build_exposure_mapping
from app.modules.operational_events.schemas import OperationalEventCreate
from app.modules.operational_events.service import create_operational_event
from app.schemas.context import RequestContext


def test_projected_exhaustion_within_48h_creates_immediate_exposure() -> None:
    with seeded_exposure_session(on_hand=Decimal("10"), daily_consumption=Decimal("10")) as (
        db,
        tenant,
        plant,
        material,
        _,
    ):
        exposure = build_exposure_mapping(
            db,
            context_for(tenant),
            plant_reference=plant.code,
            material_reference=material.code,
            now=NOW,
        )

        assert exposure.exposure_level == "immediate"
        assert exposure.exposure_basis == "projected_stockout"
        assert exposure.days_until_exposure == Decimal("1.00")


def test_projected_exhaustion_within_5_days_creates_near_term_exposure() -> None:
    with seeded_exposure_session(on_hand=Decimal("40"), daily_consumption=Decimal("10")) as (
        db,
        tenant,
        plant,
        material,
        _,
    ):
        exposure = build_exposure_mapping(
            db,
            context_for(tenant),
            plant_reference=plant.code,
            material_reference=material.code,
            now=NOW,
        )

        assert exposure.exposure_level == "near_term"
        assert exposure.exposure_basis == "projected_stockout"
        assert exposure.days_until_exposure == Decimal("4.00")


def test_doc_less_than_or_equal_10_creates_watch_exposure() -> None:
    with seeded_exposure_session(on_hand=Decimal("80"), daily_consumption=Decimal("10")) as (
        db,
        tenant,
        plant,
        material,
        _,
    ):
        exposure = build_exposure_mapping(
            db,
            context_for(tenant),
            plant_reference=plant.code,
            material_reference=material.code,
            now=NOW,
        )

        assert exposure.exposure_level == "watch"
        assert exposure.exposure_basis == "projected_stockout"
        assert exposure.days_until_exposure == Decimal("8.00")


def test_degraded_shipment_plus_low_cover_produces_inbound_delay_basis() -> None:
    with seeded_exposure_session(
        on_hand=Decimal("20"),
        daily_consumption=Decimal("10"),
        include_shipment=True,
    ) as (db, tenant, _, _, shipment):
        exposure = build_exposure_mapping(
            db,
            context_for(tenant),
            shipment_reference=shipment.shipment_id,
            now=NOW,
        )

        assert exposure.exposure_level == "immediate"
        assert exposure.exposure_basis == "inbound_delay_against_cover"
        assert exposure.shipment_reference == "SHIP-1"
        assert "inbound_delay_against_cover" in exposure.related_risk_types


def test_missing_consumption_returns_unknown_not_fake_precision() -> None:
    with seeded_exposure_session(on_hand=Decimal("20"), daily_consumption=Decimal("0")) as (
        db,
        tenant,
        plant,
        material,
        _,
    ):
        exposure = build_exposure_mapping(
            db,
            context_for(tenant),
            plant_reference=plant.code,
            material_reference=material.code,
            now=NOW,
        )

        assert exposure.exposure_level == "unknown"
        assert exposure.exposure_basis == "unknown"
        assert exposure.estimated_exposure_date is None
        assert exposure.days_until_exposure is None


def test_exposure_includes_trust_summary() -> None:
    with seeded_exposure_session(on_hand=Decimal("20"), daily_consumption=Decimal("10")) as (
        db,
        tenant,
        plant,
        material,
        _,
    ):
        create_event(
            db,
            tenant.id,
            plant_reference=plant.code,
            material_reference=material.code,
            confidence_score=Decimal("40"),
            freshness_status=OperationalEventFreshnessStatus.STALE,
        )
        db.commit()

        exposure = build_exposure_mapping(
            db,
            context_for(tenant),
            plant_reference=plant.code,
            material_reference=material.code,
            now=NOW,
        )

        assert exposure.trust_summary.lowest_confidence_score == Decimal("40.00")
        assert exposure.trust_summary.worst_freshness_status == "stale"
        assert "Operational signal freshness is stale" in exposure.trust_summary.warnings


def test_exposure_includes_related_risk_candidate_types() -> None:
    with seeded_exposure_session(on_hand=Decimal("20"), daily_consumption=Decimal("10")) as (
        db,
        tenant,
        plant,
        material,
        _,
    ):
        exposure = build_exposure_mapping(
            db,
            context_for(tenant),
            plant_reference=plant.code,
            material_reference=material.code,
            now=NOW,
        )

        assert "days_of_cover_breach" in exposure.related_risk_types
        assert "projected_stockout" in exposure.related_risk_types


def test_exposure_includes_timeline_event_count() -> None:
    with seeded_exposure_session(on_hand=Decimal("20"), daily_consumption=Decimal("10")) as (
        db,
        tenant,
        plant,
        material,
        _,
    ):
        create_event(db, tenant.id, plant_reference=plant.code, material_reference=material.code)
        create_event(db, tenant.id, plant_reference=plant.code, material_reference=material.code)
        db.commit()

        exposure = build_exposure_mapping(
            db,
            context_for(tenant),
            plant_reference=plant.code,
            material_reference=material.code,
            now=NOW,
        )

        assert exposure.timeline_event_count == 2


def test_exposure_mapping_preserves_tenant_isolation() -> None:
    with seeded_exposure_session(on_hand=Decimal("20"), daily_consumption=Decimal("10")) as (
        db,
        tenant_a,
        _,
        _,
        _,
    ):
        tenant_b = Tenant(name="Tenant B", slug="tenant-b")
        db.add(tenant_b)
        db.flush()
        plant_b = Plant(tenant_id=tenant_b.id, code="P2", name="Plant 2", location=None)
        material_b = Material(
            tenant_id=tenant_b.id,
            code="M2",
            name="Material 2",
            category="raw",
            uom="MT",
        )
        db.add_all([plant_b, material_b])
        db.flush()
        db.add(
            StockSnapshot(
                tenant_id=tenant_b.id,
                plant_id=plant_b.id,
                material_id=material_b.id,
                on_hand_mt=Decimal("10"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("10"),
                daily_consumption_mt=Decimal("10"),
                snapshot_time=NOW,
            )
        )
        create_event(db, tenant_b.id, plant_reference="P2", material_reference="M2")
        db.commit()

        exposure = build_exposure_mapping(
            db,
            context_for(tenant_a),
            plant_reference="P2",
            material_reference="M2",
            now=NOW,
        )

        assert exposure.exposure_level == "unknown"
        assert exposure.timeline_event_count == 0
        assert exposure.related_risk_types == []


NOW = datetime(2026, 5, 9, 12, tzinfo=UTC)


class seeded_exposure_session:
    def __init__(
        self,
        *,
        on_hand: Decimal,
        daily_consumption: Decimal,
        include_shipment: bool = False,
    ) -> None:
        self.on_hand = on_hand
        self.daily_consumption = daily_consumption
        self.include_shipment = include_shipment

    def __enter__(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.session_local = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
        )
        Base.metadata.create_all(bind=self.engine)
        self.db = self.session_local()
        tenant = Tenant(name="Tenant A", slug="tenant-a")
        self.db.add(tenant)
        self.db.flush()
        plant = Plant(tenant_id=tenant.id, code="P1", name="Plant 1", location=None)
        material = Material(
            tenant_id=tenant.id,
            code="M1",
            name="Material 1",
            category="raw",
            uom="MT",
        )
        self.db.add_all([plant, material])
        self.db.flush()
        shipment = None
        if self.include_shipment:
            shipment = Shipment(
                tenant_id=tenant.id,
                shipment_id="SHIP-1",
                material_id=material.id,
                plant_id=plant.id,
                supplier_name="Supplier 1",
                quantity_mt=Decimal("50"),
                planned_eta=NOW + timedelta(days=1),
                current_eta=NOW + timedelta(days=4),
                latest_eta=NOW + timedelta(days=1),
                current_milestone="in_transit",
                last_tracking_update_at=NOW - timedelta(hours=8),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="manual_upload",
                latest_update_at=NOW - timedelta(hours=8),
            )
            self.db.add(shipment)
        self.db.add(
            StockSnapshot(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                on_hand_mt=self.on_hand,
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=self.on_hand,
                daily_consumption_mt=self.daily_consumption,
                snapshot_time=NOW,
            )
        )
        self.db.commit()
        return self.db, tenant, plant, material, shipment

    def __exit__(self, exc_type, exc_value, traceback):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)


def create_event(
    db: Session,
    tenant_id: int,
    *,
    event_type: OperationalEventType = OperationalEventType.INVENTORY_STOCK_UPDATED,
    event_category: OperationalEventCategory = OperationalEventCategory.INVENTORY,
    plant_reference: str | None = "P1",
    material_reference: str | None = "M1",
    shipment_reference: str | None = None,
    confidence_score: Decimal | None = None,
    freshness_status: OperationalEventFreshnessStatus | None = None,
):
    return create_operational_event(
        db,
        OperationalEventCreate(
            tenant_id=tenant_id,
            event_type=event_type,
            event_category=event_category,
            source_type=OperationalEventSourceType.FILE_INGESTION,
            source_reference="file_ingestion",
            occurred_at=NOW,
            detected_at=NOW,
            plant_reference=plant_reference,
            material_reference=material_reference,
            shipment_reference=shipment_reference,
            quantity_value=Decimal("20"),
            quantity_unit="MT",
            new_value={"available_to_consume_mt": "20"},
            confidence_score=confidence_score,
            freshness_status=freshness_status,
        ),
    )


def context_for(tenant: Tenant) -> RequestContext:
    return RequestContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        role="tenant_admin",
        user_id=1,
    )
