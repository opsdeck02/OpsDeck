from __future__ import annotations

from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import ExternalDataSource, Plant, Role, Tenant, TenantMembership, User
from app.modules.auth.constants import BUYER_USER, TENANT_ADMIN
from app.modules.auth.security import hash_password


def test_tenant_plan_defaults_and_gates_data_sources() -> None:
    engine, testing_session = build_test_db()
    with testing_session() as db:
        tenant = seed_tenant_data(db, plan_tier="pilot")

    override_database(testing_session)
    try:
        client = TestClient(app)
        admin_token = login(client, "admin@test.local", "Password123!")

        plan_response = client.get(
            "/api/v1/tenants/plan",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Tenant-Slug": "demo-tenant",
            },
        )
        assert plan_response.status_code == 200
        assert plan_response.json()["plan_tier"] == "pilot"
        assert plan_response.json()["capabilities"]["automated_data_sources"] is False

        create_response = client.post(
            "/api/v1/tenants/data-sources",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Tenant-Slug": "demo-tenant",
            },
            json={
                "source_type": "google_sheets",
                "source_url": "https://docs.google.com/spreadsheets/d/example",
                "source_name": "Inbound sheet",
                "dataset_type": "shipments",
                "mapping_config": {"shipment_id": "A"},
                "sync_frequency_minutes": 60,
                "is_active": True,
            },
        )
        assert create_response.status_code == 403
        assert "paid or enterprise" in create_response.json()["detail"]

        with testing_session() as db:
            refreshed = db.get(Tenant, tenant.id)
            assert refreshed is not None
            assert refreshed.plan_tier == "pilot"
    finally:
        cleanup_database(engine)


def test_superadmin_can_upgrade_tenant_in_place_and_paid_tenant_can_save_data_source() -> None:
    engine, testing_session = build_test_db()
    with testing_session() as db:
        tenant = seed_tenant_data(db, plan_tier="pilot")
        original_tenant_id = tenant.id

    override_database(testing_session)
    try:
        client = TestClient(app)
        superadmin_token = login(client, "superadmin@test.local", "SuperAdmin123!")
        admin_token = login(client, "admin@test.local", "Password123!")

        update_response = client.patch(
            f"/api/v1/tenants/admin/{original_tenant_id}/plan",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"plan_tier": "paid"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["plan_tier"] == "paid"
        assert update_response.json()["capabilities"]["automated_data_sources"] is True

        create_response = client.post(
            "/api/v1/tenants/data-sources",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Tenant-Slug": "demo-tenant",
            },
            json={
                "source_type": "excel_online",
                "source_url": "https://contoso.sharepoint.com/sites/ops/workbook.xlsx",
                "source_name": "Stock workbook",
                "dataset_type": "stock",
                "mapping_config": {"plant": "B"},
                "sync_frequency_minutes": 120,
                "is_active": True,
            },
        )
        assert create_response.status_code == 200
        assert create_response.json()["source_type"] == "excel_online"

        list_response = client.get(
            "/api/v1/tenants/data-sources",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Tenant-Slug": "demo-tenant",
            },
        )
        assert list_response.status_code == 200
        assert len(list_response.json()) == 1

        with testing_session() as db:
            refreshed = db.get(Tenant, original_tenant_id)
            assert refreshed is not None
            assert refreshed.id == original_tenant_id
            assert refreshed.plan_tier == "paid"
            assert db.scalar(select(TenantMembership).where(TenantMembership.tenant_id == original_tenant_id)) is not None
            assert db.scalar(select(Plant).where(Plant.tenant_id == original_tenant_id, Plant.code == "P1")) is not None
            assert db.scalar(select(ExternalDataSource).where(ExternalDataSource.tenant_id == original_tenant_id)) is not None
    finally:
        cleanup_database(engine)


def build_test_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    return engine, testing_session


def override_database(testing_session) -> None:
    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db


def cleanup_database(engine) -> None:
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def seed_tenant_data(db: Session, *, plan_tier: str) -> Tenant:
    tenant = Tenant(name="Demo Tenant", slug="demo-tenant", max_users=10, plan_tier=plan_tier)
    db.add(tenant)
    roles = [
        Role(name=TENANT_ADMIN, description="Tenant admin"),
        Role(name=BUYER_USER, description="Buyer"),
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
    tenant_admin = User(
        email="admin@test.local",
        full_name="Tenant Admin",
        password_hash=hash_password("Password123!"),
        is_active=True,
        is_superadmin=False,
    )
    buyer = User(
        email="buyer@test.local",
        full_name="Buyer User",
        password_hash=hash_password("Password123!"),
        is_active=True,
        is_superadmin=False,
    )
    db.add_all([superadmin, tenant_admin, buyer])
    db.flush()

    tenant_admin_role = db.scalar(select(Role).where(Role.name == TENANT_ADMIN))
    buyer_role = db.scalar(select(Role).where(Role.name == BUYER_USER))
    db.add_all(
        [
            TenantMembership(
                tenant_id=tenant.id,
                user_id=tenant_admin.id,
                role_id=tenant_admin_role.id,
                is_active=True,
            ),
            TenantMembership(
                tenant_id=tenant.id,
                user_id=buyer.id,
                role_id=buyer_role.id,
                is_active=True,
            ),
        ]
    )
    db.add(Plant(tenant_id=tenant.id, code="P1", name="Plant 1", location=None))
    db.commit()
    db.refresh(tenant)
    return tenant


def login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return str(response.json()["access_token"])
