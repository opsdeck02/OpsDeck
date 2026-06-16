from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import (
    LineStopIncident,
    Material,
    Plant,
    PlantMaterialThreshold,
    Role,
    Shipment,
    StockSnapshot,
    Supplier,
    Tenant,
    TenantMembership,
    User,
)
from app.models.enums import ShipmentState
from app.modules.auth.constants import LOGISTICS_USER
from app.modules.auth.security import hash_password
from app.modules.line_stops.service import build_historical_validation_report
from app.schemas.context import RequestContext


def test_historical_validation_report_calculates_warning_lead_time() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            tenant = seed_historical_validation_data(db)
            report = build_historical_validation_report(
                db,
                RequestContext(
                    tenant_id=tenant.id,
                    tenant_slug=tenant.slug,
                    role="tenant_admin",
                    user_id=1,
                ),
            )

        assert report.total_incidents == 1
        assert report.incidents_with_warning == 1
        assert report.results[0].predicted_warning_date == datetime(2026, 6, 6, tzinfo=UTC)
        assert report.results[0].lead_time_gained_hours == Decimal("96.00")
        assert report.results[0].confidence_level == "high"
        assert report.results[0].opsdeck_detection_result == "PARTIALLY DETECTED"
        assert report.results[0].warning_lead_time_days == Decimal("4.00")
        assert "Days of Cover Breach" in report.results[0].detection_signals
        assert report.summary is not None
        assert report.summary.incidents_analyzed == 1
        assert report.summary.partially_detected == 1
        assert report.report_markdown is not None
        assert "Past Incident Analysis" in report.report_markdown
        assert "It is not statistical ML validation" in report.report_markdown
        assert "Recommended Actions Replay" in report.report_markdown
        result = report.results[0]
        assert result.replay_caveat is not None
        assert "not statistical ML validation" in result.replay_caveat
        assert result.stock_snapshot_time_used == datetime(2026, 6, 1, tzinfo=UTC)
        assert result.available_stock_at_snapshot == Decimal("100.00")
        assert result.daily_consumption_used == Decimal("10.00")
        assert result.threshold_days_used == Decimal("2.00")
        assert result.warning_days_used == Decimal("5.00")
        assert result.status_explanation == (
            "OpsDeck found some warning signs, but the available data was incomplete or late."
        )
    finally:
        Base.metadata.drop_all(bind=engine)


def test_historical_validation_v2_summary_and_incident_classification() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            tenant = seed_mixed_historical_validation_data(db)
            report = build_historical_validation_report(
                db,
                RequestContext(
                    tenant_id=tenant.id,
                    tenant_slug=tenant.slug,
                    role="tenant_admin",
                    user_id=1,
                ),
            )

        assert report.summary is not None
        assert report.summary.incidents_analyzed == 3
        assert report.summary.detected == 1
        assert report.summary.partially_detected == 1
        assert report.summary.missed == 1
        assert report.summary.detection_rate_percent == Decimal("33.33")
        assert report.summary.average_warning_lead_time_days == Decimal("4.00")
        assert report.summary.longest_warning_lead_time_days == Decimal("4.00")
        assert report.summary.shortest_warning_lead_time_days == Decimal("4.00")

        by_material = {result.material_reference: result for result in report.results}
        detected = by_material["COKE"]
        assert detected.opsdeck_detection_result == "DETECTED"
        assert detected.earliest_detection_date == datetime(2026, 6, 6, tzinfo=UTC)
        assert detected.warning_lead_time_hours == Decimal("96.00")
        assert detected.warning_lead_time_days == Decimal("4.00")
        assert detected.confidence_classification == "HIGH CONFIDENCE"
        assert detected.missed_incident_analysis == []
        assert detected.detection_chain
        assert detected.recommended_actions_replay

        partial = by_material["PCI"]
        assert partial.opsdeck_detection_result == "PARTIALLY DETECTED"
        assert partial.confidence_classification == "MEDIUM CONFIDENCE"
        assert partial.missed_incident_analysis == [
            "No linked inbound shipments were available before incident."
        ]

        missed = by_material["ORE"]
        assert missed.opsdeck_detection_result == "MISSED"
        assert missed.confidence_classification == "LOW CONFIDENCE"
        assert missed.detection_signals == []
        assert missed.missed_incident_analysis == [
            "No stock snapshot existed before the incident date."
        ]
        assert "No stock snapshot available before incident." in missed.missing_data_limitations

        late = by_material["COKE"]
        assert any(
            "SHIP-COKE-LATE" in limitation and "late" in limitation.lower()
            for limitation in late.missing_data_limitations
        )
    finally:
        Base.metadata.drop_all(bind=engine)


def test_historical_validation_is_tenant_scoped() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            tenant_a = seed_historical_validation_data(db)
            tenant_b = Tenant(name="Tenant B", slug="tenant-b")
            db.add(tenant_b)
            db.flush()
            plant_b = Plant(
                tenant_id=tenant_b.id,
                code="P1",
                name="Other Plant",
                location="India",
            )
            material_b = Material(
                tenant_id=tenant_b.id,
                code="COKE",
                name="Other Coking coal",
                category="coal",
                uom="MT",
            )
            db.add_all([plant_b, material_b])
            db.flush()
            db.add(
                LineStopIncident(
                    tenant_id=tenant_b.id,
                    plant_id=plant_b.id,
                    material_id=material_b.id,
                    stopped_at=datetime(2026, 6, 12, tzinfo=UTC),
                    duration_hours=Decimal("4"),
                )
            )
            db.commit()

            report_a = build_historical_validation_report(
                db,
                RequestContext(
                    tenant_id=tenant_a.id,
                    tenant_slug=tenant_a.slug,
                    role="tenant_admin",
                    user_id=1,
                ),
            )

        assert report_a.summary is not None
        assert report_a.summary.incidents_analyzed == 1
        assert report_a.results[0].plant_name == "Plant 1"
        assert report_a.results[0].material_name == "Coking coal"
    finally:
        Base.metadata.drop_all(bind=engine)


def test_incident_replay_missing_threshold_shows_limitation() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            tenant = Tenant(name="Tenant A", slug="tenant-a")
            db.add(tenant)
            db.flush()
            plant = Plant(tenant_id=tenant.id, code="P1", name="Plant 1", location="India")
            material = Material(
                tenant_id=tenant.id,
                code="COKE",
                name="Coking coal",
                category="coal",
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
                    quality_held_mt=Decimal("0"),
                    available_to_consume_mt=Decimal("100"),
                    daily_consumption_mt=Decimal("10"),
                    snapshot_time=datetime(2026, 6, 1, tzinfo=UTC),
                )
            )
            db.add(
                LineStopIncident(
                    tenant_id=tenant.id,
                    plant_id=plant.id,
                    material_id=material.id,
                    stopped_at=datetime(2026, 6, 10, tzinfo=UTC),
                    duration_hours=Decimal("8"),
                )
            )
            db.commit()
            report = build_historical_validation_report(
                db,
                RequestContext(
                    tenant_id=tenant.id,
                    tenant_slug=tenant.slug,
                    role="tenant_admin",
                    user_id=1,
                ),
            )

        result = report.results[0]
        assert result.threshold_days_used is None
        assert "Thresholds missing for this material." in result.missing_data_limitations
    finally:
        Base.metadata.drop_all(bind=engine)


def test_historical_validation_endpoint_returns_report() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            tenant = seed_historical_validation_data(db)
            seed_login_user(db, tenant)

        def override_get_db() -> Generator[Session, None, None]:
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"email": "planner@test.local", "password": "TestOnlyCredential1!"},
            )
            token = login.json()["access_token"]
            response = client.get(
                "/api/v1/line-stops/historical-validation",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Slug": "tenant-a",
                },
            )

        assert response.status_code == 200
        assert response.json()["total_incidents"] == 1
        assert response.json()["results"][0]["lead_time_gained_hours"] == "96.00"
        assert response.json()["summary"]["incidents_analyzed"] == 1
        assert response.json()["results"][0]["opsdeck_detection_result"] == (
            "PARTIALLY DETECTED"
        )
        assert response.json()["results"][0]["warning_lead_time_days"] == "4.00"
        assert response.json()["report_markdown"]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def seed_historical_validation_data(db: Session) -> Tenant:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    db.add(tenant)
    db.flush()
    plant = Plant(tenant_id=tenant.id, code="P1", name="Plant 1", location="India")
    material = Material(
        tenant_id=tenant.id,
        code="COKE",
        name="Coking coal",
        category="coal",
        uom="MT",
    )
    db.add_all([plant, material])
    db.flush()
    db.add_all(
        [
            StockSnapshot(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                on_hand_mt=Decimal("100"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("100"),
                daily_consumption_mt=Decimal("10"),
                snapshot_time=datetime(2026, 6, 1, tzinfo=UTC),
            ),
            PlantMaterialThreshold(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                threshold_days=Decimal("2"),
                warning_days=Decimal("5"),
                minimum_buffer_stock_days=Decimal("3"),
            ),
            LineStopIncident(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                stopped_at=datetime(2026, 6, 10, tzinfo=UTC),
                duration_hours=Decimal("8"),
            ),
        ]
    )
    db.commit()
    return tenant


def seed_mixed_historical_validation_data(db: Session) -> Tenant:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    db.add(tenant)
    db.flush()
    plant = Plant(tenant_id=tenant.id, code="P1", name="Plant 1", location="India")
    materials = {
        "COKE": Material(
            tenant_id=tenant.id,
            code="COKE",
            name="Coking coal",
            category="coal",
            uom="MT",
        ),
        "PCI": Material(
            tenant_id=tenant.id,
            code="PCI",
            name="PCI coal",
            category="coal",
            uom="MT",
        ),
        "ORE": Material(
            tenant_id=tenant.id,
            code="ORE",
            name="Iron ore fines",
            category="ore",
            uom="MT",
        ),
    }
    supplier = Supplier(
        tenant_id=tenant.id,
        name="Reliable Supplier",
        code="SUP-1",
        primary_port="DEMO Destination A",
        is_active=True,
    )
    db.add_all([plant, supplier, *materials.values()])
    db.flush()
    for material in materials.values():
        db.add(
            PlantMaterialThreshold(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                threshold_days=Decimal("2"),
                warning_days=Decimal("5"),
                minimum_buffer_stock_days=Decimal("3"),
            )
        )
    for code in ("COKE", "PCI"):
        db.add(
            StockSnapshot(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=materials[code].id,
                on_hand_mt=Decimal("100"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("100"),
                daily_consumption_mt=Decimal("10"),
                snapshot_time=datetime(2026, 6, 1, tzinfo=UTC),
            )
        )
    db.add(
        Shipment(
            tenant_id=tenant.id,
            shipment_id="SHIP-COKE-1",
            plant_id=plant.id,
            material_id=materials["COKE"].id,
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            quantity_mt=Decimal("10"),
            planned_eta=datetime(2026, 6, 7, tzinfo=UTC),
            current_eta=datetime(2026, 6, 7, tzinfo=UTC),
            delay_status="on_time",
            current_state=ShipmentState.IN_TRANSIT,
            source_of_truth="historical_upload",
            latest_update_at=datetime(2026, 6, 5, tzinfo=UTC),
        )
    )
    db.add(
        Shipment(
            tenant_id=tenant.id,
            shipment_id="SHIP-COKE-LATE",
            plant_id=plant.id,
            material_id=materials["COKE"].id,
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            quantity_mt=Decimal("50"),
            planned_eta=datetime(2026, 6, 12, tzinfo=UTC),
            current_eta=datetime(2026, 6, 12, tzinfo=UTC),
            delay_status="late",
            current_state=ShipmentState.IN_TRANSIT,
            source_of_truth="historical_upload",
            latest_update_at=datetime(2026, 6, 5, tzinfo=UTC),
        )
    )
    for material in materials.values():
        db.add(
            LineStopIncident(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                stopped_at=datetime(2026, 6, 10, tzinfo=UTC),
                duration_hours=Decimal("8"),
            )
        )
    db.commit()
    return tenant


def seed_login_user(db: Session, tenant: Tenant) -> None:
    role = Role(name=LOGISTICS_USER, description="Logistics")
    user = User(
        email="planner@test.local",
        full_name="Planner",
        password_hash=hash_password("TestOnlyCredential1!"),
        is_active=True,
    )
    db.add_all([role, user])
    db.flush()
    db.add(
        TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            role_id=role.id,
            is_active=True,
        )
    )
    db.commit()
