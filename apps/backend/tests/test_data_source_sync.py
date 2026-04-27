from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import ExternalDataSource, Material, Plant, Role, Shipment, Tenant, TenantMembership, User
from app.modules.auth.constants import TENANT_ADMIN
from app.modules.auth.security import hash_password
from app.modules.tenants import sync_service


def test_google_sheets_sync_success_updates_registry_and_ingests_rows(monkeypatch) -> None:
    engine, testing_session = build_test_db()
    with testing_session() as db:
        seed_sync_data(db, tenant_plan="paid")

    monkeypatch.setattr(
        sync_service,
        "fetch_url_bytes",
        lambda url: (
            shipment_csv_bytes(),
            "text/csv",
        ),
    )

    override_database(testing_session)
    try:
        client = TestClient(app)
        token = login(client, "admin@paid.local", "Password123!")

        create_response = client.post(
            "/api/v1/tenants/data-sources",
            headers=tenant_headers(token, "paid-tenant"),
            json={
                "source_type": "google_sheets",
                "source_url": "https://docs.google.com/spreadsheets/d/sheet123/edit#gid=0",
                "source_name": "Inbound shipments",
                "dataset_type": "shipments",
                "mapping_config": {"sheet_gid": "0"},
                "sync_frequency_minutes": 60,
                "is_active": True,
            },
        )
        assert create_response.status_code == 200
        source_id = create_response.json()["id"]

        sync_response = client.post(
            f"/api/v1/tenants/data-sources/{source_id}/sync",
            headers=tenant_headers(token, "paid-tenant"),
        )
        assert sync_response.status_code == 200
        body = sync_response.json()
        assert body["sync_status"] == "succeeded"
        assert body["rows_received"] == 1
        assert body["rows_accepted"] == 1
        assert body["rows_rejected"] == 0
        assert body["validation_summary"]["created"] == 1
        assert body["last_synced_at"] is not None

        with testing_session() as db:
            source = db.get(ExternalDataSource, source_id)
            assert source is not None
            assert source.last_sync_status == "succeeded"
            assert source.last_synced_at is not None
            assert source.last_error_message is None
            assert db.scalar(
                select(func.count(Shipment.id)).where(Shipment.tenant_id == source.tenant_id)
            ) == 1
    finally:
        cleanup_database(engine)


def test_excel_online_sync_success_with_xlsx_and_tenant_isolation(monkeypatch) -> None:
    engine, testing_session = build_test_db()
    with testing_session() as db:
        seed_sync_data(db, tenant_plan="paid")

    monkeypatch.setattr(
        sync_service,
        "fetch_url_bytes",
        lambda url: (stock_xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    )

    override_database(testing_session)
    try:
        client = TestClient(app)
        token = login(client, "admin@paid.local", "Password123!")

        create_response = client.post(
            "/api/v1/tenants/data-sources",
            headers=tenant_headers(token, "paid-tenant"),
            json={
                "source_type": "excel_online",
                "source_url": "https://contoso.sharepoint.com/sites/ops/stock.xlsx",
                "source_name": "Stock workbook",
                "dataset_type": "stock",
                "mapping_config": {},
                "sync_frequency_minutes": 60,
                "is_active": True,
            },
        )
        assert create_response.status_code == 200
        source_id = create_response.json()["id"]

        sync_response = client.post(
            f"/api/v1/tenants/data-sources/{source_id}/sync",
            headers=tenant_headers(token, "paid-tenant"),
        )
        assert sync_response.status_code == 200
        assert sync_response.json()["sync_status"] == "succeeded"

        with testing_session() as db:
            paid_tenant = db.scalar(select(Tenant).where(Tenant.slug == "paid-tenant"))
            other_tenant = db.scalar(select(Tenant).where(Tenant.slug == "other-tenant"))
            assert paid_tenant is not None
            assert other_tenant is not None
            paid_shipments = db.scalar(
                select(func.count(Shipment.id)).where(Shipment.tenant_id == paid_tenant.id)
            )
            other_shipments = db.scalar(
                select(func.count(Shipment.id)).where(Shipment.tenant_id == other_tenant.id)
            )
            assert paid_shipments == 0
            assert other_shipments == 1
    finally:
        cleanup_database(engine)


def test_invalid_excel_link_fails_gracefully_and_updates_error_state() -> None:
    engine, testing_session = build_test_db()
    with testing_session() as db:
        seed_sync_data(db, tenant_plan="paid")

    override_database(testing_session)
    try:
        client = TestClient(app)
        token = login(client, "admin@paid.local", "Password123!")
        create_response = client.post(
            "/api/v1/tenants/data-sources",
            headers=tenant_headers(token, "paid-tenant"),
            json={
                "source_type": "excel_online",
                "source_url": "https://contoso.sharepoint.com/sites/ops/view.aspx?id=123",
                "source_name": "Bad link",
                "dataset_type": "shipments",
                "mapping_config": {},
                "sync_frequency_minutes": 60,
                "is_active": True,
            },
        )
        source_id = create_response.json()["id"]

        sync_response = client.post(
            f"/api/v1/tenants/data-sources/{source_id}/sync",
            headers=tenant_headers(token, "paid-tenant"),
        )
        assert sync_response.status_code == 200
        body = sync_response.json()
        assert body["sync_status"] == "failed"
        assert "direct downloadable" in body["last_error"]

        with testing_session() as db:
            source = db.get(ExternalDataSource, source_id)
            assert source is not None
            assert source.last_sync_status == "failed"
            assert source.last_synced_at is not None
            assert "direct downloadable" in str(source.last_error_message)
    finally:
        cleanup_database(engine)


def test_pilot_tenant_is_blocked_from_sync_now() -> None:
    engine, testing_session = build_test_db()
    with testing_session() as db:
        seed_sync_data(db, tenant_plan="pilot")

    override_database(testing_session)
    try:
        client = TestClient(app)
        token = login(client, "admin@paid.local", "Password123!")
        create_response = client.post(
            "/api/v1/tenants/data-sources",
            headers=tenant_headers(token, "paid-tenant"),
            json={
                "source_type": "google_sheets",
                "source_url": "https://docs.google.com/spreadsheets/d/sheet123/edit#gid=0",
                "source_name": "Blocked source",
                "dataset_type": "shipments",
                "mapping_config": {},
                "sync_frequency_minutes": 60,
                "is_active": True,
            },
        )
        assert create_response.status_code == 403
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


def seed_sync_data(db: Session, *, tenant_plan: str) -> None:
    paid_tenant = Tenant(name="Paid Tenant", slug="paid-tenant", plan_tier=tenant_plan)
    other_tenant = Tenant(name="Other Tenant", slug="other-tenant", plan_tier="paid")
    admin_role = Role(name=TENANT_ADMIN, description="Admin")
    db.add_all([paid_tenant, other_tenant, admin_role])
    db.flush()

    admin = User(
        email="admin@paid.local",
        full_name="Paid Admin",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    db.add(admin)
    db.flush()
    db.add(
        TenantMembership(
            tenant_id=paid_tenant.id,
            user_id=admin.id,
            role_id=admin_role.id,
            is_active=True,
        )
    )

    now = datetime.now(UTC)
    db.add_all(
        [
            Plant(tenant_id=paid_tenant.id, code="P1", name="Plant 1", location="India"),
            Material(
                tenant_id=paid_tenant.id,
                code="COAL",
                name="Coal",
                category="coal",
                uom="MT",
            ),
            Plant(tenant_id=other_tenant.id, code="P1", name="Plant 1", location="India"),
            Material(
                tenant_id=other_tenant.id,
                code="COAL",
                name="Coal",
                category="coal",
                uom="MT",
            ),
        ]
    )
    db.flush()

    other_plant = db.scalar(select(Plant).where(Plant.tenant_id == other_tenant.id))
    other_material = db.scalar(select(Material).where(Material.tenant_id == other_tenant.id))
    db.add(
        Shipment(
            tenant_id=other_tenant.id,
            shipment_id="OTHER-1",
            material_id=other_material.id,
            plant_id=other_plant.id,
            supplier_name="Other Supplier",
            quantity_mt=Decimal("100"),
            vessel_name="MV Other",
            imo_number=None,
            mmsi=None,
            origin_port="Port",
            destination_port="Plant",
            planned_eta=now + timedelta(days=2),
            current_eta=now + timedelta(days=2),
            eta_confidence=Decimal("80"),
            current_state="at_sea",
            source_of_truth="seed",
            latest_update_at=now,
        )
    )
    db.commit()


def shipment_csv_bytes() -> bytes:
    return (
        "shipment_id,plant_code,material_code,supplier_name,quantity_mt,planned_eta,current_eta,current_state,source_of_truth,latest_update_at\n"
        "SYNC-1,P1,COAL,Supplier One,120,2026-04-22T10:00:00Z,2026-04-22T10:00:00Z,in_transit,sync,2026-04-21T10:00:00Z\n"
    ).encode("utf-8")


def stock_xlsx_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "plant_code",
            "material_code",
            "on_hand_mt",
            "quality_held_mt",
            "available_to_consume_mt",
            "daily_consumption_mt",
            "snapshot_time",
        ]
    )
    sheet.append(["P1", "COAL", "150", "0", "150", "50", "2026-04-21T10:00:00Z"])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return str(response.json()["access_token"])


def tenant_headers(token: str, tenant_slug: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Slug": tenant_slug,
    }
