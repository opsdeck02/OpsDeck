from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import Material, Plant, Role, Shipment, Supplier, Tenant, TenantMembership, User
from app.models.enums import ShipmentState
from app.modules.auth.constants import TENANT_ADMIN
from app.modules.auth.security import hash_password
from app.modules.ingestion.service import process_upload_content
from app.schemas.context import RequestContext


def client_with_db() -> Generator[tuple[TestClient, sessionmaker], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        seed_base(db)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), TestingSessionLocal
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def test_supplier_crud_linking_and_performance() -> None:
    for client, _ in client_with_db():
        headers = auth_headers(client)
        created = client.post(
            "/api/v1/suppliers",
            headers=headers,
            json={
                "name": "Acme Coal",
                "code": "ACME",
                "primary_port": "Hay Point",
                "material_categories": ["coal"],
            },
        )
        assert created.status_code == 200
        supplier = created.json()

        patched = client.patch(
            f"/api/v1/suppliers/{supplier['id']}",
            headers=headers,
            json={"country_of_origin": "Australia", "contact_name": "Ops Lead"},
        )
        assert patched.status_code == 200
        assert patched.json()["country_of_origin"] == "Australia"

        linked = client.post(
            f"/api/v1/suppliers/{supplier['id']}/link-shipments",
            headers=headers,
        )
        assert linked.status_code == 200
        assert linked.json()["linked_shipments"] == 2

        detail = client.get(f"/api/v1/suppliers/{supplier['id']}", headers=headers)
        assert detail.status_code == 200
        body = detail.json()
        assert body["performance"]["total_shipments"] == 2
        assert body["performance"]["active_shipments"] == 2
        assert body["performance"]["on_time_reliability_pct"] == "50.00"
        assert body["performance"]["avg_eta_drift_hours"] == "30.00"
        assert body["performance"]["reliability_grade"] == "C"
        assert body["performance"]["materials_supplied"] == ["Coking Coal"]
        assert len(body["linked_shipments"]) == 2

        deleted = client.delete(f"/api/v1/suppliers/{supplier['id']}", headers=headers)
        assert deleted.status_code == 200
        assert deleted.json()["is_active"] is False


def test_supplier_summary_best_and_worst() -> None:
    for client, _ in client_with_db():
        headers = auth_headers(client)
        for payload in [
            {"name": "Acme Coal", "code": "ACME"},
            {"name": "Late Coal", "code": "LATE"},
        ]:
            response = client.post("/api/v1/suppliers", headers=headers, json=payload)
            assert response.status_code == 200
            link = client.post(
                f"/api/v1/suppliers/{response.json()['id']}/link-shipments",
                headers=headers,
            )
            assert link.status_code == 200

        summary = client.get("/api/v1/suppliers/performance/summary", headers=headers)
        assert summary.status_code == 200
        body = summary.json()
        assert body["top_suppliers"][0]["performance"]["reliability_grade"] in {"A", "C"}
        assert body["bottom_suppliers"][0]["performance"]["reliability_grade"] in {"C", "D"}


def test_ingestion_auto_links_supplier_by_name() -> None:
    for _, SessionLocal in client_with_db():
        with SessionLocal() as db:
            tenant = db.scalar(select(Tenant).where(Tenant.slug == "tenant-a"))
            user = db.scalar(select(User).where(User.email == "admin@test.local"))
            supplier = Supplier(
                tenant_id=tenant.id,
                name="Beta Coal",
                code="BETA",
                is_active=True,
            )
            db.add(supplier)
            db.commit()
            context = RequestContext(
                tenant_id=tenant.id,
                tenant_slug=tenant.slug,
                role=TENANT_ADMIN,
                user_id=user.id,
            )
            content = (
                "shipment_id,plant_code,material_code,supplier_name,quantity_mt,"
                "planned_eta,current_eta,current_state,latest_update_at\n"
                "BETA-1,JAM,COAL,Beta Coal,100,"
                "2026-01-01T00:00:00+00:00,2026-01-01T12:00:00+00:00,"
                "in_transit,2025-12-30T00:00:00+00:00\n"
            ).encode()
            result = process_upload_content(
                db=db,
                context=context,
                current_user_id=user.id,
                file_type="shipment",
                filename="shipment.csv",
                content=content,
                content_type="text/csv",
                source_of_truth="manual_upload",
            )
            assert result.rows_accepted == 1
            shipment = db.scalar(select(Shipment).where(Shipment.shipment_id == "BETA-1"))
            assert shipment is not None
            assert shipment.supplier_id == supplier.id


def test_reliability_grade_boundaries() -> None:
    from app.modules.suppliers.service import reliability_grade

    assert reliability_grade(Decimal("85.00")) == "A"
    assert reliability_grade(Decimal("70.00")) == "B"
    assert reliability_grade(Decimal("50.00")) == "C"
    assert reliability_grade(Decimal("49.99")) == "D"


def seed_base(db: Session) -> None:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    role = Role(name=TENANT_ADMIN, description="Tenant admin")
    db.add_all([tenant, role])
    db.flush()
    user = User(
        email="admin@test.local",
        full_name="Admin",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role_id=role.id))
    plant = Plant(tenant_id=tenant.id, code="JAM", name="Jamshedpur", location="IN")
    material = Material(tenant_id=tenant.id, code="COAL", name="Coking Coal", category="coal")
    db.add_all([plant, material])
    db.flush()
    now = datetime.now(UTC)
    db.add_all(
        [
            Shipment(
                tenant_id=tenant.id,
                shipment_id="ACME-ON-TIME",
                plant_id=plant.id,
                material_id=material.id,
                supplier_name="Acme Coal",
                quantity_mt=Decimal("100"),
                planned_eta=now + timedelta(days=1),
                current_eta=now + timedelta(days=1, hours=12),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="manual_upload",
                latest_update_at=now - timedelta(hours=2),
            ),
            Shipment(
                tenant_id=tenant.id,
                shipment_id="ACME-LATE",
                plant_id=plant.id,
                material_id=material.id,
                supplier_name="Acme Coal",
                quantity_mt=Decimal("100"),
                planned_eta=now + timedelta(days=2),
                current_eta=now + timedelta(days=4),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="manual_upload",
                latest_update_at=now - timedelta(days=8),
            ),
            Shipment(
                tenant_id=tenant.id,
                shipment_id="LATE-1",
                plant_id=plant.id,
                material_id=material.id,
                supplier_name="Late Coal",
                quantity_mt=Decimal("100"),
                planned_eta=now + timedelta(days=1),
                current_eta=now + timedelta(days=5),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="manual_upload",
                latest_update_at=now - timedelta(days=8),
            ),
        ]
    )
    db.commit()


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.local", "password": "Password123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
