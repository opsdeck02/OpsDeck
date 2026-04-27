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
    ShipmentUpdate,
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
        seed_shipments(db)

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


def seed_shipments(db: Session) -> None:
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
    ship_only = Shipment(
        tenant_id=tenant_a.id,
        shipment_id="SHIP-SEA-1",
        material_id=material_a.id,
        plant_id=plant_a.id,
        supplier_name="Supplier A",
        quantity_mt=Decimal("1000"),
        vessel_name="MV Alpha",
        imo_number="1234567",
        mmsi="999999999",
        origin_port="Hay Point",
        destination_port="Paradip",
        planned_eta=now + timedelta(days=6),
        current_eta=now + timedelta(days=7),
        eta_confidence=Decimal("84"),
        current_state=ShipmentState.IN_TRANSIT,
        source_of_truth="manual_upload",
        latest_update_at=now - timedelta(hours=6),
    )
    port_ship = Shipment(
        tenant_id=tenant_a.id,
        shipment_id="SHIP-PORT-1",
        material_id=material_a.id,
        plant_id=plant_a.id,
        supplier_name="Supplier B",
        quantity_mt=Decimal("2000"),
        vessel_name="MV Beta",
        imo_number="7654321",
        mmsi="888888888",
        origin_port="Gladstone",
        destination_port="Paradip",
        planned_eta=now + timedelta(days=2),
        current_eta=now + timedelta(days=2),
        eta_confidence=Decimal("76"),
        current_state=ShipmentState.IN_TRANSIT,
        source_of_truth="manual_upload",
        latest_update_at=now - timedelta(hours=5),
    )
    inland_ship = Shipment(
        tenant_id=tenant_a.id,
        shipment_id="SHIP-INLAND-1",
        material_id=material_a.id,
        plant_id=plant_a.id,
        supplier_name="Supplier C",
        quantity_mt=Decimal("1500"),
        vessel_name=None,
        imo_number=None,
        mmsi=None,
        origin_port="Paradip",
        destination_port="JAM yard",
        planned_eta=now + timedelta(days=1),
        current_eta=now + timedelta(days=1),
        eta_confidence=Decimal("90"),
        current_state=ShipmentState.INLAND_TRANSIT,
        source_of_truth="manual_upload",
        latest_update_at=now - timedelta(hours=3),
    )
    delivered_ship = Shipment(
        tenant_id=tenant_a.id,
        shipment_id="SHIP-DONE-1",
        material_id=material_a.id,
        plant_id=plant_a.id,
        supplier_name="Supplier D",
        quantity_mt=Decimal("1200"),
        vessel_name=None,
        imo_number=None,
        mmsi=None,
        origin_port=None,
        destination_port=None,
        planned_eta=now - timedelta(days=1),
        current_eta=now - timedelta(days=1),
        eta_confidence=Decimal("100"),
        current_state=ShipmentState.DELIVERED,
        source_of_truth="manual_upload",
        latest_update_at=now - timedelta(hours=2),
    )
    cancelled_ship = Shipment(
        tenant_id=tenant_a.id,
        shipment_id="SHIP-CANCEL-1",
        material_id=material_a.id,
        plant_id=plant_a.id,
        supplier_name="Supplier E",
        quantity_mt=Decimal("900"),
        vessel_name="MV Gamma",
        imo_number=None,
        mmsi=None,
        origin_port=None,
        destination_port=None,
        planned_eta=now + timedelta(days=4),
        current_eta=now + timedelta(days=4),
        eta_confidence=Decimal("0"),
        current_state=ShipmentState.CANCELLED,
        source_of_truth="manual_upload",
        latest_update_at=now - timedelta(hours=1),
    )
    tenant_b_ship = Shipment(
        tenant_id=tenant_b.id,
        shipment_id="SHIP-B-1",
        material_id=material_b.id,
        plant_id=plant_b.id,
        supplier_name="Supplier Z",
        quantity_mt=Decimal("500"),
        vessel_name="MV Other",
        imo_number=None,
        mmsi=None,
        origin_port=None,
        destination_port=None,
        planned_eta=now + timedelta(days=3),
        current_eta=now + timedelta(days=3),
        eta_confidence=Decimal("88"),
        current_state=ShipmentState.IN_TRANSIT,
        source_of_truth="manual_upload",
        latest_update_at=now - timedelta(hours=1),
    )
    db.add_all([ship_only, port_ship, inland_ship, delivered_ship, cancelled_ship, tenant_b_ship])
    db.flush()

    db.add(
        PortEvent(
            tenant_id=tenant_a.id,
            shipment_id=port_ship.id,
            berth_status="waiting",
            waiting_days=Decimal("1.5"),
            discharge_started_at=None,
            discharge_rate_mt_per_day=None,
            estimated_demurrage_exposure=Decimal("12000"),
        )
    )
    db.add(
        InlandMovement(
            tenant_id=tenant_a.id,
            shipment_id=inland_ship.id,
            mode="rail",
            carrier_name="Indian Railways",
            origin_location="Paradip",
            destination_location="JAM Yard",
            planned_departure_at=now - timedelta(hours=10),
            planned_arrival_at=now + timedelta(hours=18),
            actual_departure_at=now - timedelta(hours=9),
            actual_arrival_at=None,
            current_state="en_route",
        )
    )
    db.add(
        ShipmentUpdate(
            tenant_id=tenant_a.id,
            shipment_id=ship_only.id,
            source="manual_upload",
            event_type="eta_refresh",
            event_time=now - timedelta(hours=6),
            payload_json=None,
            notes="ETA refreshed",
        )
    )
    db.commit()


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ops@test.local", "password": "Password123!"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": "tenant-a"}


def test_shipment_state_derivation_from_shipment_only_data(client: TestClient) -> None:
    response = client.get("/api/v1/shipments/visibility", headers=auth_headers(client))
    body = response.json()
    ship = next(item for item in body if item["shipment_id"] == "SHIP-SEA-1")
    assert ship["shipment_state"] == "on_water"


def test_state_derivation_with_port_event_present(client: TestClient) -> None:
    response = client.get("/api/v1/shipments/SHIP-PORT-1", headers=auth_headers(client))
    assert response.status_code == 200
    assert response.json()["shipment"]["shipment_state"] == "at_port"


def test_state_derivation_with_inland_movement_present(client: TestClient) -> None:
    response = client.get("/api/v1/shipments/SHIP-INLAND-1", headers=auth_headers(client))
    assert response.status_code == 200
    assert response.json()["shipment"]["shipment_state"] == "in_transit"
    assert response.json()["shipment"]["latest_status_source"] == "inland_movement"


def test_delivered_cancelled_exclusion_behavior(client: TestClient) -> None:
    delivered = client.get("/api/v1/shipments/SHIP-DONE-1", headers=auth_headers(client)).json()
    cancelled = client.get("/api/v1/shipments/SHIP-CANCEL-1", headers=auth_headers(client)).json()
    assert delivered["shipment"]["contribution_band"] == "excluded"
    assert cancelled["shipment"]["contribution_band"] == "excluded"


def test_filter_behavior_in_shipment_list_api(client: TestClient) -> None:
    response = client.get(
        "/api/v1/shipments/visibility?state=at_port&search=PORT",
        headers=auth_headers(client),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["shipment_id"] == "SHIP-PORT-1"


def test_tenant_isolation_behavior(client: TestClient) -> None:
    response = client.get("/api/v1/shipments/visibility", headers=auth_headers(client))
    assert response.status_code == 200
    shipment_ids = {item["shipment_id"] for item in response.json()}
    assert "SHIP-B-1" not in shipment_ids
