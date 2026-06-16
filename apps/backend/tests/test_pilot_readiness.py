from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    IngestionJob,
    Material,
    Plant,
    PlantMaterialThreshold,
    Shipment,
    StockSnapshot,
    Tenant,
)
from app.models.enums import ShipmentState
from app.modules.dashboard.service import build_pilot_readiness
from app.schemas.context import RequestContext


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_pilot_readiness_incomplete_when_stock_missing(db_session: Session) -> None:
    tenant, plant, material = seed_core_entities(db_session)
    add_threshold(db_session, tenant, plant, material)
    add_shipment(db_session, tenant, plant, material)

    readiness = build_pilot_readiness(db_session, context_for(tenant))

    assert readiness.setup_status == "Pilot setup incomplete"
    assert readiness.safe_to_rely_on is False
    assert checklist_state(readiness, "upload_stock") == "Not started"


def test_pilot_readiness_incomplete_when_consumption_missing(db_session: Session) -> None:
    tenant, plant, material = seed_core_entities(db_session)
    add_stock(db_session, tenant, plant, material, daily_consumption=Decimal("0"))
    add_threshold(db_session, tenant, plant, material)
    add_shipment(db_session, tenant, plant, material)

    readiness = build_pilot_readiness(db_session, context_for(tenant))

    assert readiness.setup_status == "Pilot setup incomplete"
    assert readiness.safe_to_rely_on is False
    assert checklist_state(readiness, "confirm_consumption") == "Not started"


def test_pilot_readiness_incomplete_when_thresholds_missing(db_session: Session) -> None:
    tenant, plant, material = seed_core_entities(db_session)
    add_stock(db_session, tenant, plant, material)
    add_shipment(db_session, tenant, plant, material)

    readiness = build_pilot_readiness(db_session, context_for(tenant))

    assert readiness.setup_status == "Pilot setup incomplete"
    assert readiness.safe_to_rely_on is False
    assert checklist_state(readiness, "upload_thresholds") == "Not started"


def test_pilot_readiness_needs_review_when_new_master_data_exists(
    db_session: Session,
) -> None:
    tenant, plant, material = seed_ready_data(db_session)
    db_session.add(
        IngestionJob(
            tenant_id=tenant.id,
            source_type="stock",
            status="completed",
            records_total=1,
            records_succeeded=1,
            records_failed=0,
            metadata_json={
                "operational_summary": {
                    "new_materials_created": ["DOVLI-COKE"],
                    "new_plants_created": [],
                    "new_suppliers_created": [],
                }
            },
        )
    )
    db_session.flush()

    readiness = build_pilot_readiness(db_session, context_for(tenant))

    assert plant.id is not None
    assert material.id is not None
    assert readiness.setup_status == "Pilot setup needs review"
    assert readiness.safe_to_rely_on is False
    assert checklist_state(readiness, "review_master_data") == "Needs attention"


def test_pilot_readiness_ready_when_mandatory_setup_complete(db_session: Session) -> None:
    tenant, _, _ = seed_ready_data(db_session)

    readiness = build_pilot_readiness(db_session, context_for(tenant))

    assert readiness.setup_status == "Pilot setup ready for guided review"
    assert readiness.safe_to_rely_on is True
    assert readiness.safe_to_rely_on_reason == "Pilot setup is ready for guided review."
    mandatory_states = {
        item.key: item.state
        for item in readiness.setup_checklist
        if item.category == "mandatory"
    }
    assert set(mandatory_states.values()) == {"Complete"}


def seed_ready_data(db: Session) -> tuple[Tenant, Plant, Material]:
    tenant, plant, material = seed_core_entities(db)
    add_stock(db, tenant, plant, material)
    add_threshold(db, tenant, plant, material)
    add_shipment(db, tenant, plant, material)
    db.flush()
    return tenant, plant, material


def seed_core_entities(db: Session) -> tuple[Tenant, Plant, Material]:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    db.add(tenant)
    db.flush()
    plant = Plant(tenant_id=tenant.id, code="DOLVI", name="Dolvi", location="Maharashtra")
    material = Material(
        tenant_id=tenant.id,
        code="COKE",
        name="Coking Coal",
        category="raw",
        uom="MT",
    )
    db.add_all([plant, material])
    db.flush()
    return tenant, plant, material


def add_stock(
    db: Session,
    tenant: Tenant,
    plant: Plant,
    material: Material,
    *,
    daily_consumption: Decimal = Decimal("100"),
) -> None:
    db.add(
        StockSnapshot(
            tenant_id=tenant.id,
            plant_id=plant.id,
            material_id=material.id,
            on_hand_mt=Decimal("1000"),
            quality_held_mt=Decimal("0"),
            available_to_consume_mt=Decimal("1000"),
            daily_consumption_mt=daily_consumption,
            snapshot_time=datetime.now(UTC) - timedelta(hours=2),
        )
    )
    db.flush()


def add_threshold(db: Session, tenant: Tenant, plant: Plant, material: Material) -> None:
    db.add(
        PlantMaterialThreshold(
            tenant_id=tenant.id,
            plant_id=plant.id,
            material_id=material.id,
            threshold_days=Decimal("3"),
            warning_days=Decimal("7"),
        )
    )
    db.flush()


def add_shipment(db: Session, tenant: Tenant, plant: Plant, material: Material) -> None:
    now = datetime.now(UTC)
    db.add(
        Shipment(
            tenant_id=tenant.id,
            shipment_id="SHIP-001",
            material_id=material.id,
            plant_id=plant.id,
            supplier_name="ABC Minerals",
            quantity_mt=Decimal("500"),
            vessel_name=None,
            imo_number=None,
            mmsi=None,
            origin_port=None,
            destination_port=None,
            planned_eta=now + timedelta(days=2),
            current_eta=now + timedelta(days=2),
            latest_eta=now + timedelta(days=2),
            delay_days=0,
            delay_status="on_time",
            current_milestone="in_transit",
            current_location="Mumbai",
            last_tracking_update_at=now - timedelta(hours=4),
            eta_confidence=Decimal("0.90"),
            current_state=ShipmentState.IN_TRANSIT,
            source_of_truth="manual_upload",
            latest_update_at=now - timedelta(hours=4),
        )
    )
    db.flush()


def context_for(tenant: Tenant) -> RequestContext:
    return RequestContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        role="tenant_admin",
        user_id=1,
    )


def checklist_state(readiness, key: str) -> str:
    return next(item.state for item in readiness.setup_checklist if item.key == key)
