from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import (
    InlandMovement,
    Material,
    Plant,
    PlantMaterialThreshold,
    PortEvent,
    Role,
    Shipment,
    StockSnapshot,
    Tenant,
    TenantMembership,
    User,
)
from app.models.enums import ShipmentState
from app.modules.auth.constants import LOGISTICS_USER
from app.modules.auth.security import hash_password


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        seed_stock_cover_data(db)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
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


def seed_stock_cover_data(db: Session) -> None:
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    role = Role(name=LOGISTICS_USER, description="Logistics")
    db.add_all([tenant_a, tenant_b, role])
    db.flush()

    user = User(
        email="planner@test.local",
        full_name="Planner",
        password_hash=hash_password("Password123!"),
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

    plants = {
        code: Plant(tenant_id=tenant_a.id, code=code, name=f"Plant {code}", location="India")
        for code in ("P1", "P2", "P3", "P4", "P5")
    }
    plants["B1"] = Plant(tenant_id=tenant_b.id, code="B1", name="Tenant B Plant", location="India")
    materials = {
        code: Material(
            tenant_id=tenant_a.id,
            code=code,
            name=f"Material {code}",
            category="raw",
            uom="MT",
        )
        for code in ("M1", "M2", "M3", "M4", "M5")
    }
    materials["B1"] = Material(
        tenant_id=tenant_b.id,
        code="B1",
        name="Tenant B Material",
        category="raw",
        uom="MT",
    )
    db.add_all(list(plants.values()) + list(materials.values()))
    db.flush()

    now = datetime.now(UTC)
    db.add_all(
        [
            PlantMaterialThreshold(
                tenant_id=tenant_a.id,
                plant_id=plants["P1"].id,
                material_id=materials["M1"].id,
                threshold_days=Decimal("5"),
                warning_days=Decimal("8"),
            ),
            PlantMaterialThreshold(
                tenant_id=tenant_a.id,
                plant_id=plants["P2"].id,
                material_id=materials["M2"].id,
                threshold_days=Decimal("5"),
                warning_days=Decimal("8"),
            ),
            PlantMaterialThreshold(
                tenant_id=tenant_a.id,
                plant_id=plants["P3"].id,
                material_id=materials["M3"].id,
                threshold_days=Decimal("5"),
                warning_days=Decimal("8"),
            ),
            PlantMaterialThreshold(
                tenant_id=tenant_a.id,
                plant_id=plants["P4"].id,
                material_id=materials["M4"].id,
                threshold_days=Decimal("5"),
                warning_days=Decimal("8"),
            ),
        ]
    )
    db.add_all(
        [
            StockSnapshot(
                tenant_id=tenant_a.id,
                plant_id=plants["P1"].id,
                material_id=materials["M1"].id,
                on_hand_mt=Decimal("1000"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("1000"),
                daily_consumption_mt=Decimal("100"),
                snapshot_time=now - timedelta(hours=3),
            ),
            StockSnapshot(
                tenant_id=tenant_a.id,
                plant_id=plants["P2"].id,
                material_id=materials["M2"].id,
                on_hand_mt=Decimal("650"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("650"),
                daily_consumption_mt=Decimal("100"),
                snapshot_time=now - timedelta(hours=10),
            ),
            StockSnapshot(
                tenant_id=tenant_a.id,
                plant_id=plants["P3"].id,
                material_id=materials["M3"].id,
                on_hand_mt=Decimal("350"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("350"),
                daily_consumption_mt=Decimal("100"),
                snapshot_time=now - timedelta(hours=80),
            ),
            StockSnapshot(
                tenant_id=tenant_a.id,
                plant_id=plants["P4"].id,
                material_id=materials["M4"].id,
                on_hand_mt=Decimal("350"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("350"),
                daily_consumption_mt=Decimal("0"),
                snapshot_time=now - timedelta(hours=2),
            ),
            StockSnapshot(
                tenant_id=tenant_a.id,
                plant_id=plants["P5"].id,
                material_id=materials["M5"].id,
                on_hand_mt=Decimal("1200"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("1200"),
                daily_consumption_mt=Decimal("100"),
                snapshot_time=now - timedelta(hours=5),
            ),
            StockSnapshot(
                tenant_id=tenant_b.id,
                plant_id=plants["B1"].id,
                material_id=materials["B1"].id,
                on_hand_mt=Decimal("999"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("999"),
                daily_consumption_mt=Decimal("10"),
                snapshot_time=now - timedelta(hours=1),
            ),
        ]
    )
    db.add_all(
        [
            Shipment(
                tenant_id=tenant_a.id,
                shipment_id="SAFE-PIPE",
                material_id=materials["M1"].id,
                plant_id=plants["P1"].id,
                supplier_name="Supplier",
                quantity_mt=Decimal("500"),
                vessel_name=None,
                imo_number=None,
                mmsi=None,
                origin_port=None,
                destination_port=None,
                planned_eta=now + timedelta(days=2),
                current_eta=now + timedelta(days=2),
                eta_confidence=Decimal("90"),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="test",
                latest_update_at=now - timedelta(hours=5),
            ),
            Shipment(
                tenant_id=tenant_a.id,
                shipment_id="IGNORE-CANCELLED",
                material_id=materials["M2"].id,
                plant_id=plants["P2"].id,
                supplier_name="Supplier",
                quantity_mt=Decimal("900"),
                vessel_name=None,
                imo_number=None,
                mmsi=None,
                origin_port=None,
                destination_port=None,
                planned_eta=now + timedelta(days=3),
                current_eta=now + timedelta(days=3),
                eta_confidence=Decimal("70"),
                current_state=ShipmentState.CANCELLED,
                source_of_truth="test",
                latest_update_at=now - timedelta(hours=4),
            ),
            Shipment(
                tenant_id=tenant_a.id,
                shipment_id="SEA-LOW",
                material_id=materials["M2"].id,
                plant_id=plants["P2"].id,
                supplier_name="Supplier",
                quantity_mt=Decimal("400"),
                vessel_name="MV Ocean",
                imo_number="1234567",
                mmsi="7654321",
                origin_port="Hay Point",
                destination_port="Paradip",
                planned_eta=now + timedelta(days=4),
                current_eta=now + timedelta(days=4),
                eta_confidence=Decimal("60"),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="test",
                latest_update_at=now - timedelta(days=5),
            ),
            Shipment(
                tenant_id=tenant_a.id,
                shipment_id="INLAND-HIGH",
                material_id=materials["M2"].id,
                plant_id=plants["P2"].id,
                supplier_name="Supplier",
                quantity_mt=Decimal("400"),
                vessel_name=None,
                imo_number=None,
                mmsi=None,
                origin_port="Paradip",
                destination_port="Plant P2",
                planned_eta=now + timedelta(hours=18),
                current_eta=now + timedelta(hours=18),
                eta_confidence=Decimal("92"),
                current_state=ShipmentState.INLAND_TRANSIT,
                source_of_truth="test",
                latest_update_at=now - timedelta(hours=3),
            ),
            Shipment(
                tenant_id=tenant_a.id,
                shipment_id="PORT-STALE",
                material_id=materials["M3"].id,
                plant_id=plants["P3"].id,
                supplier_name="Supplier",
                quantity_mt=Decimal("200"),
                vessel_name="MV Port",
                imo_number="9988776",
                mmsi="112233445",
                origin_port="Gladstone",
                destination_port="Paradip",
                planned_eta=now - timedelta(days=1),
                current_eta=now - timedelta(days=1),
                eta_confidence=Decimal("55"),
                current_state=ShipmentState.AT_PORT,
                source_of_truth="test",
                latest_update_at=now - timedelta(days=4),
            ),
            Shipment(
                tenant_id=tenant_b.id,
                shipment_id="TENANT-B",
                material_id=materials["B1"].id,
                plant_id=plants["B1"].id,
                supplier_name="Supplier",
                quantity_mt=Decimal("111"),
                vessel_name=None,
                imo_number=None,
                mmsi=None,
                origin_port=None,
                destination_port=None,
                planned_eta=now + timedelta(days=1),
                current_eta=now + timedelta(days=1),
                eta_confidence=Decimal("99"),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="test",
                latest_update_at=now - timedelta(hours=1),
            ),
        ]
    )
    db.flush()
    inland_high = db.query(Shipment).filter(Shipment.shipment_id == "INLAND-HIGH").one()
    port_stale = db.query(Shipment).filter(Shipment.shipment_id == "PORT-STALE").one()
    db.add(
        InlandMovement(
            tenant_id=tenant_a.id,
            shipment_id=inland_high.id,
            mode="rail",
            carrier_name="Indian Railways",
            origin_location="Paradip",
            destination_location="Plant P2",
            planned_departure_at=now - timedelta(hours=5),
            planned_arrival_at=now + timedelta(hours=12),
            actual_departure_at=now - timedelta(hours=4),
            actual_arrival_at=None,
            current_state="en_route",
        )
    )
    db.add(
        PortEvent(
            tenant_id=tenant_a.id,
            shipment_id=port_stale.id,
            berth_status="waiting",
            waiting_days=Decimal("3"),
            discharge_started_at=None,
            discharge_rate_mt_per_day=None,
            estimated_demurrage_exposure=Decimal("12000"),
            updated_at=now - timedelta(days=5),
        )
    )
    db.commit()


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "planner@test.local", "password": "Password123!"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": "tenant-a"}


def stock_row(response_json: dict, plant_code: str, material_code: str) -> dict:
    return next(
        row
        for row in response_json["rows"]
        if row["plant_code"] == plant_code and row["material_code"] == material_code
    )


def test_normal_stock_cover_calculation(client: TestClient) -> None:
    response = client.get("/api/v1/stock/cover", headers=auth_headers(client))
    assert response.status_code == 200
    safe_row = stock_row(response.json(), "P1", "M1")
    assert safe_row["calculation"]["status"] == "safe"
    assert safe_row["calculation"]["linked_shipment_count"] == 1
    assert safe_row["calculation"]["raw_inbound_pipeline_mt"] == "500.00"
    assert safe_row["calculation"]["effective_inbound_pipeline_mt"] == "385.00"
    assert safe_row["calculation"]["days_of_cover"] == "13.85"


def test_warning_threshold_case(client: TestClient) -> None:
    response = client.get("/api/v1/stock/cover", headers=auth_headers(client))
    warning_row = stock_row(response.json(), "P2", "M2")
    assert warning_row["calculation"]["status"] == "safe"
    assert warning_row["calculation"]["days_of_cover"] == "10.70"


def test_critical_threshold_case(client: TestClient) -> None:
    response = client.get("/api/v1/stock/cover", headers=auth_headers(client))
    critical_row = stock_row(response.json(), "P3", "M3")
    assert critical_row["calculation"]["status"] == "critical"
    assert critical_row["calculation"]["confidence_level"] == "low"
    assert critical_row["calculation"]["urgency_band"] == "immediate"
    assert Decimal(critical_row["calculation"]["estimated_value_at_risk"]) > Decimal("0")
    assert critical_row["calculation"]["value_per_mt_used"] is not None
    assert critical_row["calculation"]["criticality_multiplier_used"] is not None
    assert critical_row["calculation"]["recommended_action_code"] == "validate_eta_now"
    assert critical_row["calculation"]["owner_role_recommended"] == "logistics_user"
    assert critical_row["calculation"]["action_deadline_hours"] == 4


def test_insufficient_data_case_for_zero_consumption(client: TestClient) -> None:
    response = client.get("/api/v1/stock/cover", headers=auth_headers(client))
    insufficient_row = stock_row(response.json(), "P4", "M4")
    assert insufficient_row["calculation"]["status"] == "insufficient_data"
    assert "zero or negative" in insufficient_row["calculation"]["insufficient_data_reason"]


def test_missing_threshold_behavior(client: TestClient) -> None:
    response = client.get("/api/v1/stock/cover", headers=auth_headers(client))
    missing_threshold_row = stock_row(response.json(), "P5", "M5")
    assert missing_threshold_row["calculation"]["threshold_days"] is None
    assert missing_threshold_row["calculation"]["insufficient_data_reason"] == (
        "Threshold record missing for plant/material"
    )
    assert missing_threshold_row["calculation"]["status"] == "safe"


def test_tenant_isolation_behavior(client: TestClient) -> None:
    response = client.get("/api/v1/stock/cover", headers=auth_headers(client))
    body = response.json()
    assert body["total_combinations"] == 5
    assert all(row["plant_code"] != "B1" for row in body["rows"])


def test_on_water_contributes_less_than_in_transit(client: TestClient) -> None:
    response = client.get("/api/v1/stock/cover/2/2", headers=auth_headers(client))
    assert response.status_code == 200
    body = response.json()
    sea = next(item for item in body["shipments"] if item["shipment_id"] == "SEA-LOW")
    inland = next(item for item in body["shipments"] if item["shipment_id"] == "INLAND-HIGH")
    assert Decimal(sea["contribution_factor"]) < Decimal(inland["contribution_factor"])


def test_stock_cover_detail_returns_recommendation_fields(client: TestClient) -> None:
    response = client.get("/api/v1/stock/cover/3/3", headers=auth_headers(client))
    assert response.status_code == 200
    body = response.json()
    assert body["row"]["calculation"]["recommended_action_text"] is not None
    assert body["row"]["calculation"]["owner_role_recommended"] == "logistics_user"
    assert len(body["recommendation_why"]) >= 1


def test_stock_risk_action_status_updates(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/stock/cover/3/3/action",
        headers=auth_headers(client),
        json={"action_status": "in_progress"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["row"]["calculation"]["action_status"] == "in_progress"
    assert body["row"]["calculation"]["action_age_hours"] is not None


def test_stale_low_confidence_shipment_contribution_is_reduced(client: TestClient) -> None:
    response = client.get("/api/v1/stock/cover/3/3", headers=auth_headers(client))
    assert response.status_code == 200
    shipment = response.json()["shipments"][0]
    assert shipment["freshness_label"] == "stale"
    assert shipment["confidence"] == "low"
    assert Decimal(shipment["contribution_factor"]) < Decimal("0.50")


def test_delivered_cancelled_exclusion_behavior(client: TestClient) -> None:
    response = client.get("/api/v1/stock/cover", headers=auth_headers(client))
    warning_row = stock_row(response.json(), "P2", "M2")
    assert warning_row["calculation"]["raw_inbound_pipeline_mt"] == "800.00"


def test_multiple_shipment_weighted_aggregation(client: TestClient) -> None:
    response = client.get("/api/v1/stock/cover", headers=auth_headers(client))
    warning_row = stock_row(response.json(), "P2", "M2")
    assert warning_row["calculation"]["linked_shipment_count"] == 2
    assert warning_row["calculation"]["raw_inbound_pipeline_mt"] == "800.00"
    assert warning_row["calculation"]["effective_inbound_pipeline_mt"] == "420.00"


def test_stock_cover_status_change_caused_by_refined_weighting(client: TestClient) -> None:
    response = client.get("/api/v1/stock/cover", headers=auth_headers(client))
    row = stock_row(response.json(), "P3", "M3")
    assert row["calculation"]["raw_inbound_pipeline_mt"] == "200.00"
    assert row["calculation"]["effective_inbound_pipeline_mt"] == "50.00"
    assert row["calculation"]["status"] == "critical"
