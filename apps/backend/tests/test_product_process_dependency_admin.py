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
from app.models import (
    Material,
    MaterialProcessDependency,
    Plant,
    ProcessProductDependency,
    Role,
    Tenant,
    TenantMembership,
    User,
)
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


def test_tenant_admin_can_create_update_and_list_production_lines(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_id, _ = context_ids("tenant-a")
    headers = auth_headers(client, "admin-a@test.local", "tenant-a")

    created = client.post(
        "/api/v1/impact/production-lines",
        headers=headers,
        json={"plant_id": plant_id, "code": "BF-1", "name": "Blast Furnace 1", "is_active": True},
    )
    assert created.status_code == 201
    line_id = created.json()["id"]

    updated = client.put(
        f"/api/v1/impact/production-lines/{line_id}",
        headers=headers,
        json={
            "plant_id": plant_id,
            "code": "BF-1A",
            "name": "Blast Furnace 1A",
            "is_active": False,
        },
    )
    listed = client.get(
        f"/api/v1/impact/production-lines?plant_id={plant_id}",
        headers=headers,
    )

    assert updated.status_code == 200
    assert updated.json()["code"] == "BF-1A"
    assert updated.json()["is_active"] is False
    assert listed.status_code == 200
    assert [line["id"] for line in listed.json()] == [line_id]


def test_production_line_endpoint_preserves_tenant_isolation(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_b_id, _ = context_ids("tenant-b")

    response = client.post(
        "/api/v1/impact/production-lines",
        headers=auth_headers(client, "admin-a@test.local", "tenant-a"),
        json={
            "plant_id": plant_b_id,
            "code": "BF-B",
            "name": "Other Tenant Line",
            "is_active": True,
        },
    )

    assert response.status_code == 404


def test_product_mix_row_create_update_list_and_deactivate(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, testing_session = client_and_session
    plant_id, _ = context_ids("tenant-a")
    headers = auth_headers(client, "admin-a@test.local", "tenant-a")
    line_id = create_line(client, headers, plant_id)

    created = client.post(
        "/api/v1/impact/process-product-dependencies",
        headers=headers,
        json=product_payload(line_id, product_name="HRC Coil"),
    )
    assert created.status_code == 201
    row_id = created.json()["id"]

    updated = client.put(
        f"/api/v1/impact/process-product-dependencies/{row_id}",
        headers=headers,
        json=product_payload(line_id, product_name="Billets", output_share_ratio="0.40"),
    )
    listed = client.get(
        f"/api/v1/impact/process-product-dependencies?process_id={line_id}",
        headers=headers,
    )
    deactivated = client.delete(
        f"/api/v1/impact/process-product-dependencies/{row_id}",
        headers=headers,
    )

    assert updated.status_code == 200
    assert updated.json()["product_name"] == "Billets"
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    with testing_session() as db:
        row = db.get(ProcessProductDependency, row_id)
        assert row is not None
        assert row.is_active is False


def test_product_mix_validation_constraints(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_id, _ = context_ids("tenant-a")
    headers = auth_headers(client, "admin-a@test.local", "tenant-a")
    line_id = create_line(client, headers, plant_id)

    response = client.post(
        "/api/v1/impact/process-product-dependencies",
        headers=headers,
        json=product_payload(line_id, output_share_ratio="1.50"),
    )

    assert response.status_code == 422


def test_duplicate_active_product_mix_create_is_rejected(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_id, _ = context_ids("tenant-a")
    headers = auth_headers(client, "admin-a@test.local", "tenant-a")
    line_id = create_line(client, headers, plant_id)

    first = client.post(
        "/api/v1/impact/process-product-dependencies",
        headers=headers,
        json=product_payload(line_id, product_name="HRC Coil"),
    )
    duplicate = client.post(
        "/api/v1/impact/process-product-dependencies",
        headers=headers,
        json=product_payload(line_id, product_name="hrc coil"),
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.text


def test_duplicate_active_product_mix_update_is_rejected(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_id, _ = context_ids("tenant-a")
    headers = auth_headers(client, "admin-a@test.local", "tenant-a")
    line_id = create_line(client, headers, plant_id)

    first = client.post(
        "/api/v1/impact/process-product-dependencies",
        headers=headers,
        json=product_payload(line_id, product_name="HRC Coil"),
    )
    second = client.post(
        "/api/v1/impact/process-product-dependencies",
        headers=headers,
        json=product_payload(line_id, product_name="Billets"),
    )
    duplicate_update = client.put(
        f"/api/v1/impact/process-product-dependencies/{second.json()['id']}",
        headers=headers,
        json=product_payload(line_id, product_name="HRC Coil"),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert duplicate_update.status_code == 409


def test_material_dependency_create_update_list_and_deactivate(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, testing_session = client_and_session
    plant_id, material_id = context_ids("tenant-a")
    headers = auth_headers(client, "admin-a@test.local", "tenant-a")
    line_id = create_line(client, headers, plant_id)

    created = client.post(
        "/api/v1/impact/material-process-dependencies",
        headers=headers,
        json=material_payload(material_id, line_id),
    )
    assert created.status_code == 201
    row_id = created.json()["id"]

    updated = client.put(
        f"/api/v1/impact/material-process-dependencies/{row_id}",
        headers=headers,
        json=material_payload(
            material_id,
            line_id,
            dependency_ratio="0.75",
            substitution_factor=None,
            survivability_hours=None,
        ),
    )
    listed = client.get(
        f"/api/v1/impact/material-process-dependencies?plant_id={plant_id}",
        headers=headers,
    )
    deactivated = client.delete(
        f"/api/v1/impact/material-process-dependencies/{row_id}",
        headers=headers,
    )

    assert updated.status_code == 200
    assert updated.json()["dependency_ratio"] == "0.7500"
    assert updated.json()["substitution_factor"] is None
    assert updated.json()["survivability_hours"] is None
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    with testing_session() as db:
        row = db.get(MaterialProcessDependency, row_id)
        assert row is not None
        assert row.is_active is False


def test_material_dependency_validation_and_tenant_isolation(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_a_id, _ = context_ids("tenant-a")
    _, material_b_id = context_ids("tenant-b")
    headers = auth_headers(client, "admin-a@test.local", "tenant-a")
    line_id = create_line(client, headers, plant_a_id)

    invalid_ratio = client.post(
        "/api/v1/impact/material-process-dependencies",
        headers=headers,
        json=material_payload(material_b_id, line_id, dependency_ratio="1.50"),
    )
    cross_tenant = client.post(
        "/api/v1/impact/material-process-dependencies",
        headers=headers,
        json=material_payload(material_b_id, line_id),
    )

    assert invalid_ratio.status_code == 422
    assert cross_tenant.status_code == 404


def test_duplicate_active_material_dependency_create_is_rejected(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_id, material_id = context_ids("tenant-a")
    headers = auth_headers(client, "admin-a@test.local", "tenant-a")
    line_id = create_line(client, headers, plant_id)

    first = client.post(
        "/api/v1/impact/material-process-dependencies",
        headers=headers,
        json=material_payload(material_id, line_id),
    )
    duplicate = client.post(
        "/api/v1/impact/material-process-dependencies",
        headers=headers,
        json=material_payload(material_id, line_id, dependency_ratio="0.50"),
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.text


def test_duplicate_active_material_dependency_update_is_rejected(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_id, material_id = context_ids("tenant-a")
    headers = auth_headers(client, "admin-a@test.local", "tenant-a")
    first_line_id = create_line(client, headers, plant_id)
    second_line = client.post(
        "/api/v1/impact/production-lines",
        headers=headers,
        json={
            "plant_id": plant_id,
            "code": "BF-2",
            "name": "Blast Furnace 2",
            "is_active": True,
        },
    )
    assert second_line.status_code == 201
    second_line_id = int(second_line.json()["id"])

    first = client.post(
        "/api/v1/impact/material-process-dependencies",
        headers=headers,
        json=material_payload(material_id, first_line_id),
    )
    second = client.post(
        "/api/v1/impact/material-process-dependencies",
        headers=headers,
        json=material_payload(material_id, second_line_id),
    )
    duplicate_update = client.put(
        f"/api/v1/impact/material-process-dependencies/{second.json()['id']}",
        headers=headers,
        json=material_payload(material_id, first_line_id, dependency_ratio="0.50"),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert duplicate_update.status_code == 409


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
            password_hash=hash_password("Password123!"),
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
        json={"email": email, "password": "Password123!"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": tenant_slug}


def context_ids(tenant_slug: str) -> tuple[int, int]:
    with next(app.dependency_overrides[get_db]()) as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
        assert tenant is not None
        plant = db.scalar(select(Plant).where(Plant.tenant_id == tenant.id))
        material = db.scalar(select(Material).where(Material.tenant_id == tenant.id))
        assert plant is not None
        assert material is not None
        return plant.id, material.id


def create_line(client: TestClient, headers: dict[str, str], plant_id: int) -> int:
    response = client.post(
        "/api/v1/impact/production-lines",
        headers=headers,
        json={"plant_id": plant_id, "code": "BF-1", "name": "Blast Furnace 1", "is_active": True},
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def product_payload(
    line_id: int,
    *,
    product_name: str = "HRC Coil",
    output_share_ratio: str = "0.60",
    product_value_per_mt: str = "72000",
    operational_criticality_factor: str = "1.25",
) -> dict[str, object]:
    return {
        "process_id": line_id,
        "product_name": product_name,
        "output_share_ratio": output_share_ratio,
        "product_value_per_mt": product_value_per_mt,
        "operational_criticality_factor": operational_criticality_factor,
        "is_active": True,
    }


def material_payload(
    material_id: int,
    line_id: int,
    *,
    dependency_ratio: str = "0.90",
    substitution_factor: str | None = "0.25",
    survivability_hours: str | None = "4",
) -> dict[str, object]:
    return {
        "material_id": material_id,
        "process_id": line_id,
        "dependency_ratio": dependency_ratio,
        "substitution_factor": substitution_factor,
        "survivability_hours": survivability_hours,
        "is_active": True,
    }
