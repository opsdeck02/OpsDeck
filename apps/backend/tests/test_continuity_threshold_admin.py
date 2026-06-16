from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import Material, Plant, PlantMaterialThreshold, Role, Tenant, TenantMembership, User
from app.modules.auth.constants import TENANT_ADMIN
from app.modules.auth.security import hash_password


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
        seed_data(db)

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


def test_create_threshold_config(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_id, material_id = context_ids(client, "tenant-a")

    response = client.put(
        "/api/v1/impact/continuity-thresholds",
        headers=auth_headers(client, "admin-a@test.local", "tenant-a"),
        json=payload(plant_id, material_id, warning_days="14", threshold_days="7"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plant_id"] == plant_id
    assert body["material_id"] == material_id
    assert body["warning_days"] == "14.00"
    assert body["threshold_days"] == "7.00"


def test_update_existing_threshold_config(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, testing_session = client_and_session
    plant_id, material_id = context_ids(client, "tenant-a")
    headers = auth_headers(client, "admin-a@test.local", "tenant-a")

    first = client.put(
        "/api/v1/impact/continuity-thresholds",
        headers=headers,
        json=payload(plant_id, material_id, warning_days="14", threshold_days="7"),
    )
    second = client.put(
        "/api/v1/impact/continuity-thresholds",
        headers=headers,
        json=payload(plant_id, material_id, warning_days="30", threshold_days="15"),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["warning_days"] == "30.00"
    with testing_session() as db:
        count = len(db.scalars(select(PlantMaterialThreshold)).all())
    assert count == 1


def test_warning_days_cannot_be_less_than_threshold_days(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_id, material_id = context_ids(client, "tenant-a")

    response = client.put(
        "/api/v1/impact/continuity-thresholds",
        headers=auth_headers(client, "admin-a@test.local", "tenant-a"),
        json=payload(plant_id, material_id, warning_days="3", threshold_days="7"),
    )

    assert response.status_code == 422
    assert "warning_days" in response.text


def test_threshold_endpoint_preserves_tenant_isolation(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_b_id, material_b_id = context_ids(client, "tenant-b")

    response = client.put(
        "/api/v1/impact/continuity-thresholds",
        headers=auth_headers(client, "admin-a@test.local", "tenant-a"),
        json=payload(plant_b_id, material_b_id, warning_days="14", threshold_days="7"),
    )

    assert response.status_code == 404


def test_optional_reserve_fields_are_accepted(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_id, material_id = context_ids(client, "tenant-a")

    response = client.put(
        "/api/v1/impact/continuity-thresholds",
        headers=auth_headers(client, "admin-a@test.local", "tenant-a"),
        json=payload(
            plant_id,
            material_id,
            warning_days="14",
            threshold_days="7",
            minimum_buffer_stock_days="2",
            minimum_buffer_stock_mt="500",
            reserve_quantity_mt="125",
            quality_hold_quantity_mt="75",
            stockout_alert_horizon_days="3",
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["minimum_buffer_stock_days"] == "2.00"
    assert body["minimum_buffer_stock_mt"] == "500.00"
    assert body["reserve_quantity_mt"] == "125.00"
    assert body["quality_hold_quantity_mt"] == "75.00"
    assert body["stockout_alert_horizon_days"] == "3.00"


def test_threshold_read_includes_separate_quantity_fields(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_id, material_id = context_ids(client, "tenant-a")
    headers = auth_headers(client, "admin-a@test.local", "tenant-a")

    create_response = client.put(
        "/api/v1/impact/continuity-thresholds",
        headers=headers,
        json=payload(
            plant_id,
            material_id,
            warning_days="14",
            threshold_days="7",
            minimum_buffer_stock_mt="500",
            reserve_quantity_mt="125",
            quality_hold_quantity_mt="75",
        ),
    )
    read_response = client.get(
        f"/api/v1/impact/continuity-thresholds?plant_id={plant_id}&material_id={material_id}",
        headers=headers,
    )

    assert create_response.status_code == 200, create_response.json()
    assert read_response.status_code == 200, read_response.json()
    body = read_response.json()
    assert body["minimum_buffer_stock_mt"] == "500.00"
    assert body["reserve_quantity_mt"] == "125.00"
    assert body["quality_hold_quantity_mt"] == "75.00"


def test_missing_threshold_returns_null(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_id, material_id = context_ids(client, "tenant-a")

    response = client.get(
        f"/api/v1/impact/continuity-thresholds?plant_id={plant_id}&material_id={material_id}",
        headers=auth_headers(client, "admin-a@test.local", "tenant-a"),
    )

    assert response.status_code == 200
    assert response.json() is None


def seed_data(db: Session) -> None:
    role = Role(name=TENANT_ADMIN, description="Tenant admin")
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    db.add_all([role, tenant_a, tenant_b])
    db.flush()
    for tenant, suffix in ((tenant_a, "a"), (tenant_b, "b")):
        user = User(
            email=f"admin-{suffix}@test.local",
            full_name=f"Admin {suffix.upper()}",
            password_hash=hash_password("TestOnlyCredential1!"),
            is_active=True,
        )
        plant = Plant(
            tenant_id=tenant.id,
            code=f"P{suffix.upper()}",
            name=f"Plant {suffix.upper()}",
            location="India",
        )
        material = Material(
            tenant_id=tenant.id,
            code=f"M{suffix.upper()}",
            name=f"Material {suffix.upper()}",
            category="raw",
            uom="MT",
        )
        db.add_all([user, plant, material])
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


def auth_headers(client: TestClient, email: str, tenant_slug: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "TestOnlyCredential1!"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": tenant_slug}


def context_ids(client: TestClient, tenant_slug: str) -> tuple[int, int]:
    with next(app.dependency_overrides[get_db]()) as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
        assert tenant is not None
        plant = db.scalar(select(Plant).where(Plant.tenant_id == tenant.id))
        material = db.scalar(select(Material).where(Material.tenant_id == tenant.id))
        assert plant is not None
        assert material is not None
        return plant.id, material.id


def payload(
    plant_id: int,
    material_id: int,
    *,
    warning_days: str,
    threshold_days: str,
    minimum_buffer_stock_days: str | None = None,
    minimum_buffer_stock_mt: str | None = None,
    reserve_quantity_mt: str | None = None,
    quality_hold_quantity_mt: str | None = None,
    stockout_alert_horizon_days: str | None = None,
) -> dict[str, object]:
    return {
        "plant_id": plant_id,
        "material_id": material_id,
        "warning_days": warning_days,
        "threshold_days": threshold_days,
        "minimum_buffer_stock_days": minimum_buffer_stock_days,
        "minimum_buffer_stock_mt": minimum_buffer_stock_mt,
        "reserve_quantity_mt": reserve_quantity_mt,
        "quality_hold_quantity_mt": quality_hold_quantity_mt,
        "stockout_alert_horizon_days": stockout_alert_horizon_days,
    }
