from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import (
    ExceptionCase,
    LineStopIncident,
    Material,
    Plant,
    PlantMaterialThreshold,
    Role,
    Shipment,
    StockSnapshot,
    Tenant,
    TenantMembership,
    User,
)
from app.models.enums import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    OperationalEventCategory,
    OperationalEventSourceType,
    OperationalEventType,
    ShipmentState,
)
from app.modules.auth.constants import LOGISTICS_USER
from app.modules.auth.security import hash_password
from app.modules.operational_events.schemas import OperationalEventCreate
from app.modules.operational_events.service import create_operational_event
from app.modules.reports.service import build_risk_clusters
from app.modules.rules.engine import RiskCandidate

NOW = datetime(2026, 5, 11, 9, 0, tzinfo=UTC)


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session() as db:
        seed_report_data(db)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def test_daily_continuity_brief_returns_downloadable_pdf(client: TestClient) -> None:
    response = client.get("/api/v1/reports/daily-continuity-brief", headers=auth_headers(client))

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "opsdeck-daily-continuity-brief-" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-")
    assert b"Daily Continuity Brief" in response.content
    assert b"Tenant A Steel" in response.content


def test_daily_continuity_brief_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/reports/daily-continuity-brief")

    assert response.status_code == 401


def test_daily_continuity_brief_respects_tenant_isolation(client: TestClient) -> None:
    response = client.get("/api/v1/reports/daily-continuity-brief", headers=auth_headers(client))

    assert response.status_code == 200
    assert b"COKING_COAL" in response.content
    assert b"SECRET_TENANT_B_MATERIAL" not in response.content


def test_daily_continuity_brief_groups_duplicate_risk_clusters() -> None:
    data = SimpleNamespace(
        actions=[],
        risks=[
            RiskCandidate(
                risk_type="days_of_cover_breach",
                severity="critical",
                plant_reference="JAM",
                material_reference="COKING_COAL",
                days_of_cover=Decimal("1.2"),
                continuity_status="degraded",
                freshness_status="fresh",
                rule_reasons=["Cover below threshold"],
                source_event_ids=[1],
            ),
            RiskCandidate(
                risk_type="projected_stockout",
                severity="high",
                plant_reference="JAM",
                material_reference="COKING_COAL",
                days_of_cover=Decimal("1.0"),
                continuity_status="watch",
                freshness_status="stale",
                rule_reasons=["Projected exhaustion inside window"],
                source_event_ids=[2, 3],
            ),
        ],
    )

    clusters = build_risk_clusters(data)

    assert len(clusters) == 1
    assert clusters[0].severity == "critical"
    assert clusters[0].exposure_basis == "available_cover"
    assert clusters[0].signal_count == 3
    assert clusters[0].freshness_status == "stale"


def test_executive_continuity_report_returns_executive_briefing(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/reports/executive-continuity", headers=auth_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["tenant"] == "Tenant A Steel"
    assert body["summary"]["materials_assessed"] >= 1
    assert body["summary"]["critical_materials"] + body["summary"]["high_risk_materials"] >= 1
    assert body["critical_materials"]
    material = body["critical_materials"][0]
    assert material["material_reference"] == "COKING_COAL"
    assert material["plant_reference"] == "JAM"
    assert material["assessment_calibration"] is not None
    assert material["why_escalating"]
    assert "Executive Summary" in body["markdown_report"]
    assert "Critical Materials" in body["markdown_report"]
    assert "Past Incident Analysis" in body["markdown_report"]
    assert "Incident Replay" in body["markdown_report"]
    assert body["pdf_ready_content"] == body["markdown_report"]


def test_executive_continuity_report_reuses_historical_validation_and_calibration(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/reports/executive-continuity", headers=auth_headers(client))

    assert response.status_code == 200
    body = response.json()
    historical = body["historical_validation"]
    assert historical["detected_incidents"] + historical["missed_incidents"] >= 1
    assert "detection" in historical["interpretation"].lower()
    calibration = body["critical_materials"][0]["assessment_calibration"]
    assert calibration["status"] in {
        "CALIBRATED",
        "PARTIALLY_CALIBRATED",
        "UNCALIBRATED",
        "INSUFFICIENT_DATA",
    }
    assert calibration["summary"]


def test_executive_continuity_report_supports_plant_filter(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/reports/executive-continuity",
        headers=auth_headers(client),
        params={"plant_reference": "JAM"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["plant_scope"] == "JAM"
    assert all(item["plant_reference"] == "JAM" for item in body["critical_materials"])


def test_executive_continuity_report_respects_tenant_isolation(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/reports/executive-continuity", headers=auth_headers(client))

    assert response.status_code == 200
    payload = response.text
    assert "COKING_COAL" in payload
    assert "SECRET_TENANT_B_MATERIAL" not in payload


def seed_report_data(db: Session) -> None:
    tenant_a = Tenant(name="Tenant A Steel", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B Steel", slug="tenant-b")
    role = Role(name=LOGISTICS_USER, description="Logistics")
    db.add_all([tenant_a, tenant_b, role])
    db.flush()

    user = User(
        email="ops@test.local",
        full_name="Ops User",
        password_hash=hash_password("TestOnlyCredential1!"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        TenantMembership(
            tenant_id=tenant_a.id,
            user_id=user.id,
            role_id=role.id,
            is_active=True,
        )
    )

    plant_a = Plant(tenant_id=tenant_a.id, code="JAM", name="Demo Plant A", location="Jharkhand")
    material_a = Material(
        tenant_id=tenant_a.id,
        code="COKING_COAL",
        name="Coking coal",
        category="coal",
        uom="MT",
    )
    plant_b = Plant(tenant_id=tenant_b.id, code="B", name="Tenant B Plant", location="Hidden")
    material_b = Material(
        tenant_id=tenant_b.id,
        code="SECRET_TENANT_B_MATERIAL",
        name="Hidden material",
        category="raw",
        uom="MT",
    )
    db.add_all([plant_a, material_a, plant_b, material_b])
    db.flush()

    shipment = Shipment(
        tenant_id=tenant_a.id,
        shipment_id="INB-PDP-001",
        material_id=material_a.id,
        plant_id=plant_a.id,
        supplier_name="Demo Logistics Supplier",
        quantity_mt=Decimal("50000"),
        planned_eta=NOW + timedelta(days=1),
        current_eta=NOW + timedelta(days=4),
        current_state=ShipmentState.AT_PORT,
        source_of_truth="file_ingestion",
        latest_update_at=NOW - timedelta(hours=8),
    )
    db.add_all(
        [
            StockSnapshot(
                tenant_id=tenant_a.id,
                plant_id=plant_a.id,
                material_id=material_a.id,
                on_hand_mt=Decimal("20"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("20"),
                daily_consumption_mt=Decimal("10"),
                snapshot_time=NOW,
            ),
            StockSnapshot(
                tenant_id=tenant_b.id,
                plant_id=plant_b.id,
                material_id=material_b.id,
                on_hand_mt=Decimal("100"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("100"),
                daily_consumption_mt=Decimal("5"),
                snapshot_time=NOW,
            ),
            shipment,
            PlantMaterialThreshold(
                tenant_id=tenant_a.id,
                plant_id=plant_a.id,
                material_id=material_a.id,
                threshold_days=Decimal("3"),
                warning_days=Decimal("5"),
                minimum_buffer_stock_days=Decimal("2"),
            ),
            LineStopIncident(
                tenant_id=tenant_a.id,
                plant_id=plant_a.id,
                material_id=material_a.id,
                stopped_at=NOW + timedelta(days=6),
                duration_hours=Decimal("8"),
            ),
        ]
    )
    db.flush()
    db.add(
        ExceptionCase(
            tenant_id=tenant_a.id,
            type=ExceptionType.STOCKOUT_RISK,
            severity=ExceptionSeverity.CRITICAL,
            status=ExceptionStatus.OPEN,
            title="Coking coal cover compressed",
            summary="Cover below operating buffer",
            linked_shipment_id=shipment.id,
            linked_plant_id=plant_a.id,
            linked_material_id=material_a.id,
            owner_user_id=user.id,
            triggered_at=NOW - timedelta(hours=2),
            due_at=NOW + timedelta(hours=6),
            next_action="Confirm Demo destination discharge window before next shift review.",
            action_status="pending",
        )
    )
    create_operational_event(
        db,
        OperationalEventCreate(
            tenant_id=tenant_a.id,
            event_type=OperationalEventType.INVENTORY_STOCK_UPDATED,
            event_category=OperationalEventCategory.INVENTORY,
            source_type=OperationalEventSourceType.FILE_INGESTION,
            source_reference="file_ingestion",
            occurred_at=NOW,
            detected_at=NOW,
            plant_reference=plant_a.code,
            material_reference=material_a.code,
            quantity_value=Decimal("20"),
            quantity_unit="MT",
            new_value={"available_to_consume_mt": "20"},
        ),
    )
    create_operational_event(
        db,
        OperationalEventCreate(
            tenant_id=tenant_b.id,
            event_type=OperationalEventType.INVENTORY_STOCK_UPDATED,
            event_category=OperationalEventCategory.INVENTORY,
            source_type=OperationalEventSourceType.FILE_INGESTION,
            source_reference="file_ingestion",
            occurred_at=NOW,
            detected_at=NOW,
            plant_reference=plant_b.code,
            material_reference=material_b.code,
            quantity_value=Decimal("100"),
            quantity_unit="MT",
            new_value={"available_to_consume_mt": "100"},
        ),
    )
    db.commit()


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ops@test.local", "password": "TestOnlyCredential1!"},
    )
    assert response.status_code == 200
    return {
        "Authorization": f"Bearer {response.json()['access_token']}",
        "X-Tenant-Slug": "tenant-a",
    }
