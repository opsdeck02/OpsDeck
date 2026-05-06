from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import Role, Tenant, TenantMembership, User
from app.modules.auth.constants import (
    BUYER_USER,
    LOGISTICS_USER,
    MANAGEMENT_USER,
    TENANT_ADMIN,
)
from app.modules.auth.security import hash_password


def test_superadmin_can_create_and_delete_tenant_and_tenant_admin_can_manage_users() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session() as db:
        seed_management_data(db)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        superadmin_token = login(client, "superadmin@test.local", "SuperAdmin123!")

        create_response = client.post(
            "/api/v1/tenants/admin",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={
                "name": "Alpha Metals",
                "slug": "alpha-metals",
                "max_users": 2,
                "max_plants": 3,
                "admin_user": {
                    "email": "alpha-admin@test.local",
                    "full_name": "Alpha Admin",
                    "password": "Password123!",
                },
            },
        )
        assert create_response.status_code == 200
        created_tenant = create_response.json()
        assert created_tenant["slug"] == "alpha-metals"
        assert created_tenant["max_users"] == 2
        assert created_tenant["max_plants"] == 3
        assert created_tenant["admin_user"]["email"] == "alpha-admin@test.local"
        assert created_tenant["plan_tier"] == "pilot"
        assert created_tenant["access_weeks"] == 10

        list_response = client.get(
            "/api/v1/tenants/admin/all",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )
        assert list_response.status_code == 200
        assert any(item["slug"] == "alpha-metals" for item in list_response.json())

        admin_token = login(client, "alpha-admin@test.local", "Password123!")
        create_user_response = client.post(
            "/api/v1/users",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Tenant-Slug": "alpha-metals",
            },
            json={
                "email": "buyer1@test.local",
                "full_name": "Buyer One",
                "password": "Password123!",
                "role": BUYER_USER,
            },
        )
        assert create_user_response.status_code == 200
        assert create_user_response.json()["role"] == BUYER_USER

        user_limit_response = client.post(
            "/api/v1/users",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Tenant-Slug": "alpha-metals",
            },
            json={
                "email": "logistics1@test.local",
                "full_name": "Logistics One",
                "password": "Password123!",
                "role": LOGISTICS_USER,
            },
        )
        assert user_limit_response.status_code == 400
        assert "maximum allowed users" in user_limit_response.json()["detail"]

        tenant = next(item for item in list_response.json() if item["slug"] == "alpha-metals")
        assert tenant["max_plants"] == 3
        assert tenant["active_plant_count"] == 0

        plant_limit_update = client.patch(
            f"/api/v1/tenants/admin/{tenant['id']}/plan",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"plan_tier": "pilot", "max_plants": 2},
        )
        assert plant_limit_update.status_code == 200
        assert plant_limit_update.json()["max_plants"] == 2

        superadmin_users = client.get(
            f"/api/v1/users/admin/tenant/{tenant['id']}",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )
        assert superadmin_users.status_code == 200
        assert {item["email"] for item in superadmin_users.json()} == {
            "alpha-admin@test.local",
            "buyer1@test.local",
        }

        buyer_user = next(item for item in superadmin_users.json() if item["role"] == BUYER_USER)
        profile_response = client.get(
            f"/api/v1/users/admin/tenant/{tenant['id']}/{buyer_user['id']}",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )
        assert profile_response.status_code == 200
        assert profile_response.json()["email"] == "buyer1@test.local"

        delete_response = client.delete(
            f"/api/v1/tenants/admin/{tenant['id']}",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )
        assert delete_response.status_code == 204

        final_tenants = client.get(
            "/api/v1/tenants/admin/all",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )
        assert all(item["slug"] != "alpha-metals" for item in final_tenants.json())
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def test_tenant_plant_limit_is_enforced_for_setup() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session() as db:
        seed_management_data(db)
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "demo-tenant"))
        assert tenant is not None
        tenant.max_plants = 2
        tenant_admin_role = db.scalar(select(Role).where(Role.name == TENANT_ADMIN))
        tenant_admin = User(
            email="tenant-admin@test.local",
            full_name="Tenant Admin",
            password_hash=hash_password("Password123!"),
            is_active=True,
        )
        db.add(tenant_admin)
        db.flush()
        db.add(
            TenantMembership(
                tenant_id=tenant.id,
                user_id=tenant_admin.id,
                role_id=tenant_admin_role.id,
                is_active=True,
            )
        )
        db.commit()

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        admin_token = login(client, "tenant-admin@test.local", "Password123!")

        rejected = client.post(
            "/api/v1/tenants/plants",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Tenant-Slug": "demo-tenant",
            },
            json={"count": 3, "plant_names": []},
        )
        assert rejected.status_code == 400
        assert "limited to 2 plants" in rejected.json()["detail"]

        accepted = client.post(
            "/api/v1/tenants/plants",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Tenant-Slug": "demo-tenant",
            },
            json={"count": 2, "plant_names": ["Alpha", "Beta"]},
        )
        assert accepted.status_code == 200
        assert accepted.json()["total"] == 2
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def test_superadmin_can_manually_activate_and_deactivate_tenant() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session() as db:
        seed_management_data(db)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        superadmin_token = login(client, "superadmin@test.local", "SuperAdmin123!")
        with testing_session() as db:
            tenant = db.scalar(select(Tenant).where(Tenant.slug == "demo-tenant"))
            assert tenant is not None
            tenant.access_weeks = 10
            tenant.access_expires_at = datetime.now(UTC) + timedelta(weeks=10)
            db.commit()
            tenant_id = tenant.id

        deactivate_response = client.post(
            f"/api/v1/tenants/admin/{tenant_id}/deactivate",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )
        assert deactivate_response.status_code == 200
        assert deactivate_response.json()["is_active"] is False

        activate_response = client.post(
            f"/api/v1/tenants/admin/{tenant_id}/activate",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )
        assert activate_response.status_code == 200
        assert activate_response.json()["is_active"] is True
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def seed_management_data(db: Session) -> None:
    tenant = Tenant(name="Demo Tenant", slug="demo-tenant", max_users=10)
    db.add(tenant)
    roles = [
        Role(name=TENANT_ADMIN, description="Tenant admin"),
        Role(name=BUYER_USER, description="Buyer"),
        Role(name=LOGISTICS_USER, description="Logistics"),
        Role(name=MANAGEMENT_USER, description="Management"),
    ]
    db.add_all(roles)
    db.flush()

    superadmin = User(
        email="superadmin@test.local",
        full_name="Super Admin",
        password_hash=hash_password("SuperAdmin123!"),
        is_active=True,
        is_superadmin=True,
    )
    db.add(superadmin)
    db.flush()

    tenant_admin_role = db.scalar(select(Role).where(Role.name == TENANT_ADMIN))
    db.add(
        TenantMembership(
            tenant_id=tenant.id,
            user_id=superadmin.id,
            role_id=tenant_admin_role.id,
            is_active=True,
        )
    )
    db.commit()


def login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])
