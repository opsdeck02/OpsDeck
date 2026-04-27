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
    PortEvent,
    Role,
    Shipment,
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
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session() as db:
        seed_movements(db)

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


def seed_movements(db: Session) -> None:
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    role = Role(name=LOGISTICS_USER, description="Logistics")
    db.add_all([tenant_a, tenant_b, role])
    db.flush()

    user = User(
        email="ops@test.local",
        full_name="Ops User",
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

    plant_a = Plant(tenant_id=tenant_a.id, code="JAM", name="Jamshedpur", location="Jharkhand")
    material_a = Material(
        tenant_id=tenant_a.id,
        code="COAL",
        name="Coking Coal",
        category="coal",
        uom="MT",
    )
    plant_b = Plant(tenant_id=tenant_b.id, code="B", name="Other Plant", location="West")
    material_b = Material(
        tenant_id=tenant_b.id,
        code="ORE",
        name="Iron Ore",
        category="ore",
        uom="MT",
    )
    db.add_all([plant_a, material_a, plant_b, material_b])
    db.flush()

    now = datetime.now(UTC)
    port_ship = Shipment(
        tenant_id=tenant_a.id,
        shipment_id="PORT-1",
        material_id=material_a.id,
        plant_id=plant_a.id,
        supplier_name="Supplier A",
        quantity_mt=Decimal("1200"),
        vessel_name="MV Port",
        imo_number="1111111",
        mmsi="777777777",
        origin_port="Hay Point",
        destination_port="Paradip",
        planned_eta=now + timedelta(days=1),
        current_eta=now + timedelta(days=1),
        eta_confidence=Decimal("80"),
        current_state=ShipmentState.AT_PORT,
        source_of_truth="manual_upload",
        latest_update_at=now - timedelta(hours=4),
    )
    stale_port_ship = Shipment(
        tenant_id=tenant_a.id,
        shipment_id="PORT-STALE-1",
        material_id=material_a.id,
        plant_id=plant_a.id,
        supplier_name="Supplier B",
        quantity_mt=Decimal("900"),
        vessel_name="MV Stale",
        imo_number="2222222",
        mmsi="666666666",
        origin_port="Gladstone",
        destination_port="Paradip",
        planned_eta=now - timedelta(days=1),
        current_eta=now - timedelta(days=1),
        eta_confidence=Decimal("50"),
        current_state=ShipmentState.AT_PORT,
        source_of_truth="manual_upload",
        latest_update_at=now - timedelta(days=5),
    )
    inland_ship = Shipment(
        tenant_id=tenant_a.id,
        shipment_id="INLAND-1",
        material_id=material_a.id,
        plant_id=plant_a.id,
        supplier_name="Supplier C",
        quantity_mt=Decimal("800"),
        vessel_name=None,
        imo_number=None,
        mmsi=None,
        origin_port="Paradip",
        destination_port="JAM Yard",
        planned_eta=now + timedelta(days=1),
        current_eta=now + timedelta(days=1),
        eta_confidence=Decimal("88"),
        current_state=ShipmentState.INLAND_TRANSIT,
        source_of_truth="manual_upload",
        latest_update_at=now - timedelta(hours=2),
    )
    delayed_inland_ship = Shipment(
        tenant_id=tenant_a.id,
        shipment_id="INLAND-DELAY-1",
        material_id=material_a.id,
        plant_id=plant_a.id,
        supplier_name="Supplier D",
        quantity_mt=Decimal("950"),
        vessel_name=None,
        imo_number=None,
        mmsi=None,
        origin_port="Paradip",
        destination_port="JAM Yard",
        planned_eta=now - timedelta(hours=12),
        current_eta=now + timedelta(hours=12),
        eta_confidence=Decimal("70"),
        current_state=ShipmentState.INLAND_TRANSIT,
        source_of_truth="manual_upload",
        latest_update_at=now - timedelta(hours=3),
    )
    tenant_b_ship = Shipment(
        tenant_id=tenant_b.id,
        shipment_id="TENANT-B-1",
        material_id=material_b.id,
        plant_id=plant_b.id,
        supplier_name="Supplier Z",
        quantity_mt=Decimal("700"),
        vessel_name="MV Tenant B",
        imo_number=None,
        mmsi=None,
        origin_port="Port",
        destination_port="Other",
        planned_eta=now + timedelta(days=2),
        current_eta=now + timedelta(days=2),
        eta_confidence=Decimal("80"),
        current_state=ShipmentState.AT_PORT,
        source_of_truth="manual_upload",
        latest_update_at=now - timedelta(hours=1),
    )
    db.add_all([port_ship, stale_port_ship, inland_ship, delayed_inland_ship, tenant_b_ship])
    db.flush()

    db.add_all(
        [
            PortEvent(
                tenant_id=tenant_a.id,
                shipment_id=port_ship.id,
                berth_status="waiting",
                waiting_days=Decimal("2.5"),
                discharge_started_at=None,
                discharge_rate_mt_per_day=None,
                estimated_demurrage_exposure=Decimal("10000"),
            ),
            PortEvent(
                tenant_id=tenant_a.id,
                shipment_id=stale_port_ship.id,
                berth_status="arrived",
                waiting_days=Decimal("0"),
                discharge_started_at=None,
                discharge_rate_mt_per_day=None,
                estimated_demurrage_exposure=Decimal("0"),
                updated_at=now - timedelta(days=5),
            ),
            PortEvent(
                tenant_id=tenant_b.id,
                shipment_id=tenant_b_ship.id,
                berth_status="waiting",
                waiting_days=Decimal("1"),
                discharge_started_at=None,
                discharge_rate_mt_per_day=None,
                estimated_demurrage_exposure=Decimal("5000"),
            ),
        ]
    )
    db.add_all(
        [
            InlandMovement(
                tenant_id=tenant_a.id,
                shipment_id=inland_ship.id,
                mode="rail",
                carrier_name="Indian Railways",
                origin_location="Paradip",
                destination_location="JAM Yard",
                planned_departure_at=now - timedelta(hours=8),
                planned_arrival_at=now + timedelta(hours=12),
                actual_departure_at=now - timedelta(hours=7),
                actual_arrival_at=None,
                current_state="en_route",
            ),
            InlandMovement(
                tenant_id=tenant_a.id,
                shipment_id=delayed_inland_ship.id,
                mode="road",
                carrier_name="Road Carrier",
                origin_location="Paradip",
                destination_location="JAM Yard",
                planned_departure_at=now - timedelta(days=2),
                planned_arrival_at=now - timedelta(hours=30),
                actual_departure_at=now - timedelta(days=2),
                actual_arrival_at=None,
                current_state="en_route",
            ),
        ]
    )
    db.commit()


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ops@test.local", "password": "Password123!"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": "tenant-a"}


def test_port_summary_derivation(client: TestClient) -> None:
    response = client.get("/api/v1/shipments/port-monitoring", headers=auth_headers(client))
    assert response.status_code == 200
    row = next(item for item in response.json() if item["shipment_id"] == "PORT-1")
    assert row["port_status"] == "waiting"
    assert row["likely_port_delay"] is True
    assert row["freshness"]["freshness_label"] in {"fresh", "aging"}


def test_inland_summary_derivation(client: TestClient) -> None:
    response = client.get("/api/v1/shipments/inland-monitoring", headers=auth_headers(client))
    assert response.status_code == 200
    row = next(item for item in response.json() if item["shipment_id"] == "INLAND-1")
    assert row["dispatch_status"] == "inland_dispatched"
    assert row["transporter_name"] == "Indian Railways"
    assert row["inland_delay_flag"] is False


def test_stale_record_confidence_downgrade(client: TestClient) -> None:
    response = client.get(
        "/api/v1/shipments/port-monitoring?confidence=low",
        headers=auth_headers(client),
    )
    assert response.status_code == 200
    shipment_ids = {item["shipment_id"] for item in response.json()}
    assert "PORT-STALE-1" in shipment_ids


def test_delay_heuristic_behavior(client: TestClient) -> None:
    response = client.get(
        "/api/v1/shipments/inland-monitoring?delayed_only=true",
        headers=auth_headers(client),
    )
    assert response.status_code == 200
    shipment_ids = {item["shipment_id"] for item in response.json()}
    assert "INLAND-DELAY-1" in shipment_ids
    assert "INLAND-1" not in shipment_ids


def test_combined_movement_detail_api(client: TestClient) -> None:
    response = client.get(
        "/api/v1/shipments/INLAND-DELAY-1/movement",
        headers=auth_headers(client),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["shipment"]["shipment_id"] == "INLAND-DELAY-1"
    assert body["inland_summary"]["inland_delay_flag"] is True
    assert "No port event feed is available for this shipment." in body["missing_signals"]


def test_tenant_isolation_behavior(client: TestClient) -> None:
    port_response = client.get(
        "/api/v1/shipments/port-monitoring",
        headers=auth_headers(client),
    )
    inland_response = client.get(
        "/api/v1/shipments/inland-monitoring",
        headers=auth_headers(client),
    )
    assert port_response.status_code == 200
    assert inland_response.status_code == 200
    assert "TENANT-B-1" not in {item["shipment_id"] for item in port_response.json()}
    assert "TENANT-B-1" not in {item["shipment_id"] for item in inland_response.json()}
