from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import Container, Material, Plant, Role, Shipment, Tenant, TenantMembership, User
from app.models.enums import ShipmentState
from app.modules.auth.constants import LOGISTICS_USER
from app.modules.auth.security import hash_password
from app.modules.tracking.service import calculate_delay_status, normalize_container_no


@pytest.fixture()
def client_and_session() -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session() as db:
        seed_tracking_data(db)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), testing_session
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def test_container_validation() -> None:
    assert normalize_container_no("mscu1234567") == "MSCU1234567"
    with pytest.raises(ValueError):
        normalize_container_no("MSCU123456")
    with pytest.raises(ValueError):
        normalize_container_no("MSC12345678")


def test_delay_calculation() -> None:
    planned = datetime(2026, 5, 10, tzinfo=UTC)
    assert calculate_delay_status(planned, datetime(2026, 5, 12, tzinfo=UTC)) == (2, "delayed")
    assert calculate_delay_status(planned, datetime(2026, 5, 9, tzinfo=UTC)) == (-1, "early")
    assert calculate_delay_status(planned, datetime(2026, 5, 10, tzinfo=UTC)) == (0, "on_time")
    assert calculate_delay_status(planned, None) == (None, "unknown")


def test_search_detects_carrier_and_returns_port_inland_events(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    response = client.post(
        "/api/v1/tracking/containers/search",
        headers=auth_headers(client),
        json={"container_no": "MSCU1234567"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["carrier_detection"]["carrier_code"] == "MSC"
    assert body["carrier_detection"]["requires_manual_selection"] is False
    event_types = {event["event_type"] for event in body["events"]}
    assert {"Gate in", "Vessel arrival", "Rail arrival", "Delivered"}.issubset(event_types)


def test_unknown_carrier_requires_manual_selection(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    response = client.post(
        "/api/v1/tracking/containers/search",
        headers=auth_headers(client),
        json={"container_no": "ZZZU1234567"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["carrier_detection"]["requires_manual_selection"] is True
    assert body["events"] == []


def test_linking_container_updates_shipment_tracking_status(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, SessionLocal = client_and_session
    response = client.post(
        "/api/v1/tracking/containers/link",
        headers=auth_headers(client),
        json={"container_no": "MSCU1234567", "carrier_code": "MSC", "shipment_id": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["container_no"] == "MSCU1234567"
    assert body["current_milestone"] == "Delivered"
    assert body["current_location"] == "Jamshedpur Plant"
    assert body["delay_status"] in {"delayed", "on_time", "early"}

    with SessionLocal() as db:
        shipment = db.get(Shipment, 1)
        container = db.scalar(select(Container).where(Container.container_no == "MSCU1234567"))
        assert shipment is not None
        assert container is not None
        assert shipment.latest_eta is not None
        assert shipment.current_eta == shipment.latest_eta
        assert shipment.current_milestone == "Delivered"
        assert shipment.last_tracking_update_at is not None


def seed_tracking_data(db: Session) -> None:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    role = Role(name=LOGISTICS_USER, description="Logistics")
    db.add_all([tenant, role])
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
            tenant_id=tenant.id,
            user_id=user.id,
            role_id=role.id,
            is_active=True,
        )
    )

    plant = Plant(tenant_id=tenant.id, code="JAM", name="Jamshedpur", location="Jharkhand")
    material = Material(
        tenant_id=tenant.id,
        code="COAL",
        name="Coking Coal",
        category="coal",
        uom="MT",
    )
    db.add_all([plant, material])
    db.flush()
    now = datetime.now(UTC)
    db.add(
        Shipment(
            tenant_id=tenant.id,
            shipment_id="SHIP-CONTAINER-1",
            material_id=material.id,
            plant_id=plant.id,
            supplier_name="Supplier A",
            quantity_mt=Decimal("1000"),
            vessel_name="MV Original",
            imo_number=None,
            mmsi=None,
            origin_port="Nhava Sheva",
            destination_port="Jamshedpur",
            planned_eta=now + timedelta(days=6),
            current_eta=now + timedelta(days=6),
            eta_confidence=Decimal("80"),
            current_state=ShipmentState.IN_TRANSIT,
            source_of_truth="manual_upload",
            latest_update_at=now,
        )
    )
    db.commit()


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ops@test.local", "password": "Password123!"},
    )
    assert response.status_code == 200
    return {
        "Authorization": f"Bearer {response.json()['access_token']}",
        "X-Tenant-Slug": "tenant-a",
    }
