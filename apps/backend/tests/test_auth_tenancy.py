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
from app.models import Material, Plant, Role, Shipment, Tenant, TenantMembership, User
from app.models.enums import ShipmentState
from app.modules.auth.constants import LOGISTICS_USER, SPONSOR_USER, TENANT_ADMIN
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
        seed_test_data(db)

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


def seed_test_data(db: Session) -> None:
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    admin_role = Role(name=TENANT_ADMIN, description="Admin")
    logistics_role = Role(name=LOGISTICS_USER, description="Logistics")
    sponsor_role = Role(name=SPONSOR_USER, description="Sponsor")
    db.add_all([tenant_a, tenant_b, admin_role, logistics_role, sponsor_role])
    db.flush()

    admin = User(
        email="admin@test.local",
        full_name="Admin User",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    logistics = User(
        email="logistics@test.local",
        full_name="Logistics User",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    sponsor = User(
        email="sponsor@test.local",
        full_name="Sponsor User",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    db.add_all([admin, logistics, sponsor])
    db.flush()
    plant_a = Plant(tenant_id=tenant_a.id, code="A", name="Plant A", location="East")
    plant_b = Plant(tenant_id=tenant_b.id, code="B", name="Plant B", location="West")
    material_a = Material(
        tenant_id=tenant_a.id,
        code="COAL",
        name="Coking coal",
        category="coal",
        uom="MT",
    )
    material_b = Material(
        tenant_id=tenant_b.id,
        code="ORE",
        name="Iron ore",
        category="ore",
        uom="MT",
    )
    db.add_all([plant_a, plant_b, material_a, material_b])
    db.flush()
    db.add_all(
        [
            TenantMembership(
                tenant_id=tenant_a.id,
                user_id=admin.id,
                role_id=admin_role.id,
                is_active=True,
            ),
            TenantMembership(
                tenant_id=tenant_a.id,
                user_id=logistics.id,
                role_id=logistics_role.id,
                is_active=True,
            ),
            TenantMembership(
                tenant_id=tenant_a.id,
                user_id=sponsor.id,
                role_id=sponsor_role.id,
                is_active=True,
            ),
        ]
    )
    db.add_all(
        [
            Shipment(
                tenant_id=tenant_a.id,
                shipment_id="A-001",
                material_id=material_a.id,
                plant_id=plant_a.id,
                supplier_name="Supplier A",
                quantity_mt=Decimal("1000"),
                vessel_name="MV A",
                imo_number="1111111",
                mmsi="222222222",
                origin_port="Origin A",
                destination_port="Destination A",
                planned_eta=datetime(2026, 4, 15, tzinfo=UTC),
                current_eta=datetime(2026, 4, 15, tzinfo=UTC),
                eta_confidence=Decimal("90"),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="test",
                latest_update_at=datetime(2026, 4, 14, tzinfo=UTC),
            ),
            Shipment(
                tenant_id=tenant_b.id,
                shipment_id="B-001",
                material_id=material_b.id,
                plant_id=plant_b.id,
                supplier_name="Supplier B",
                quantity_mt=Decimal("2000"),
                vessel_name="MV B",
                imo_number="3333333",
                mmsi="444444444",
                origin_port="Origin B",
                destination_port="Destination B",
                planned_eta=datetime(2026, 4, 16, tzinfo=UTC),
                current_eta=datetime(2026, 4, 16, tzinfo=UTC),
                eta_confidence=Decimal("85"),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="test",
                latest_update_at=datetime(2026, 4, 14, tzinfo=UTC),
            ),
        ]
    )
    db.commit()


def login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def test_login_and_current_user(client: TestClient) -> None:
    token = login(client, "admin@test.local")

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "admin@test.local"
    assert body["memberships"][0]["role"] == TENANT_ADMIN


def test_shipments_are_filtered_to_active_tenant(client: TestClient) -> None:
    token = login(client, "logistics@test.local")

    response = client.get(
        "/api/v1/shipments",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Slug": "tenant-a"},
    )

    assert response.status_code == 200
    references = [shipment["shipment_id"] for shipment in response.json()]
    assert references == ["A-001"]


def test_user_cannot_access_tenant_without_membership(client: TestClient) -> None:
    token = login(client, "logistics@test.local")

    response = client.get(
        "/api/v1/shipments",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Slug": "tenant-b"},
    )

    assert response.status_code == 404


def test_role_guard_allows_logistics_and_blocks_sponsor(client: TestClient) -> None:
    logistics_token = login(client, "logistics@test.local")
    sponsor_token = login(client, "sponsor@test.local")

    logistics_response = client.post(
        "/api/v1/shipments/sync",
        headers={"Authorization": f"Bearer {logistics_token}", "X-Tenant-Slug": "tenant-a"},
    )
    sponsor_response = client.post(
        "/api/v1/shipments/sync",
        headers={"Authorization": f"Bearer {sponsor_token}", "X-Tenant-Slug": "tenant-a"},
    )

    assert logistics_response.status_code == 200
    assert sponsor_response.status_code == 403


def test_expired_tenant_is_auto_deactivated_and_blocked_from_access(client: TestClient) -> None:
    with next(app.dependency_overrides[get_db]()) as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "tenant-a"))
        assert tenant is not None
        tenant.access_weeks = 10
        tenant.access_expires_at = datetime.now(UTC) - timedelta(days=1)
        tenant.is_active = True
        db.commit()

    token = login(client, "admin@test.local")

    me_response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["memberships"] == []

    shipments_response = client.get(
        "/api/v1/shipments",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Slug": "tenant-a"},
    )
    assert shipments_response.status_code == 404
