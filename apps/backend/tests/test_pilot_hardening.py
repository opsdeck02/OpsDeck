from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import (
    AuditLog,
    ExceptionCase,
    IngestionJob,
    Material,
    Plant,
    PlantMaterialThreshold,
    Role,
    Shipment,
    StockSnapshot,
    Tenant,
    TenantMembership,
    UploadedFile,
    User,
)
from app.models.enums import ExceptionSeverity, ExceptionStatus, ExceptionType, ShipmentState
from app.modules.auth.constants import LOGISTICS_USER, SPONSOR_USER, TENANT_ADMIN
from app.modules.auth.security import hash_password


def test_role_access_csv_exports_and_readiness() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session() as db:
        seed_pilot_data(db)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        admin_token = login(client, "admin@pilot.local")
        operator_token = login(client, "operator@pilot.local")
        sponsor_token = login(client, "sponsor@pilot.local")

        sponsor_upload = client.post(
            "/api/v1/ingestion/uploads",
            headers=tenant_headers(sponsor_token),
            data={"file_type": "shipment"},
            files={"file": ("shipments.csv", BytesIO(b"shipment_id\nA-1\n"), "text/csv")},
        )
        assert sponsor_upload.status_code == 403

        sponsor_evaluate = client.post(
            "/api/v1/exceptions/evaluate",
            headers=tenant_headers(sponsor_token),
        )
        assert sponsor_evaluate.status_code == 403

        operator_evaluate = client.post(
            "/api/v1/exceptions/evaluate",
            headers=tenant_headers(operator_token),
        )
        assert operator_evaluate.status_code == 200

        executive_response = client.get(
            "/api/v1/dashboard/executive",
            headers=tenant_headers(sponsor_token),
        )
        assert executive_response.status_code == 200

        stock_export = client.get(
            "/api/v1/stock/cover/export.csv",
            headers=tenant_headers(sponsor_token),
        )
        assert stock_export.status_code == 200
        assert stock_export.headers["content-type"].startswith("text/csv")
        assert "Plant One" in stock_export.text
        assert "Plant B" not in stock_export.text

        exception_export = client.get(
            "/api/v1/exceptions/export.csv",
            headers=tenant_headers(sponsor_token),
        )
        assert exception_export.status_code == 200
        assert "id,type,severity,status,title" in exception_export.text
        assert "Tenant B Exception" not in exception_export.text

        executive_export = client.get(
            "/api/v1/dashboard/executive/export.csv",
            headers=tenant_headers(sponsor_token),
        )
        assert executive_export.status_code == 200
        assert "section,label,value,status" in executive_export.text
        assert "top_risk" in executive_export.text

        readiness_for_sponsor = client.get(
            "/api/v1/dashboard/pilot-readiness",
            headers=tenant_headers(sponsor_token),
        )
        assert readiness_for_sponsor.status_code == 403

        readiness = client.get(
            "/api/v1/dashboard/pilot-readiness",
            headers=tenant_headers(admin_token),
        )
        assert readiness.status_code == 200
        body = readiness.json()
        assert body["counts"]["uploaded_files"] == 1
        assert body["counts"]["ingestion_jobs"] == 1
        assert body["counts"]["stock_cover_rows"] == 1
        assert body["counts"]["open_exceptions"] >= 1
        checks = {check["key"]: check for check in body["checks"]}
        assert checks["onboarding_uploads"]["ready"] is True
        assert checks["stock_cover_results"]["ready"] is True
        assert checks["exception_evaluation"]["ready"] is True
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def seed_pilot_data(db: Session) -> None:
    tenant_a = Tenant(name="Pilot Tenant", slug="pilot-tenant")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    admin_role = Role(name=TENANT_ADMIN, description="Admin")
    operator_role = Role(name=LOGISTICS_USER, description="Operator")
    sponsor_role = Role(name=SPONSOR_USER, description="Sponsor")
    db.add_all([tenant_a, tenant_b, admin_role, operator_role, sponsor_role])
    db.flush()

    admin = User(
        email="admin@pilot.local",
        full_name="Pilot Admin",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    operator = User(
        email="operator@pilot.local",
        full_name="Pilot Operator",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    sponsor = User(
        email="sponsor@pilot.local",
        full_name="Pilot Sponsor",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    db.add_all([admin, operator, sponsor])
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
                user_id=operator.id,
                role_id=operator_role.id,
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

    plant_a = Plant(tenant_id=tenant_a.id, code="P1", name="Plant One", location="India")
    material_a = Material(
        tenant_id=tenant_a.id,
        code="COAL",
        name="PCI Coal",
        category="coal",
        uom="MT",
    )
    plant_b = Plant(tenant_id=tenant_b.id, code="PB", name="Plant B", location="India")
    material_b = Material(
        tenant_id=tenant_b.id,
        code="ORE",
        name="Ore",
        category="ore",
        uom="MT",
    )
    db.add_all([plant_a, material_a, plant_b, material_b])
    db.flush()

    now = datetime.now(UTC)
    db.add_all(
        [
            PlantMaterialThreshold(
                tenant_id=tenant_a.id,
                plant_id=plant_a.id,
                material_id=material_a.id,
                threshold_days=Decimal("5"),
                warning_days=Decimal("7"),
            ),
            PlantMaterialThreshold(
                tenant_id=tenant_b.id,
                plant_id=plant_b.id,
                material_id=material_b.id,
                threshold_days=Decimal("5"),
                warning_days=Decimal("7"),
            ),
            StockSnapshot(
                tenant_id=tenant_a.id,
                plant_id=plant_a.id,
                material_id=material_a.id,
                on_hand_mt=Decimal("150"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("150"),
                daily_consumption_mt=Decimal("60"),
                snapshot_time=now - timedelta(hours=3),
            ),
            StockSnapshot(
                tenant_id=tenant_b.id,
                plant_id=plant_b.id,
                material_id=material_b.id,
                on_hand_mt=Decimal("200"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("200"),
                daily_consumption_mt=Decimal("50"),
                snapshot_time=now - timedelta(hours=2),
            ),
            Shipment(
                tenant_id=tenant_a.id,
                shipment_id="SHIP-A",
                material_id=material_a.id,
                plant_id=plant_a.id,
                supplier_name="Supplier A",
                quantity_mt=Decimal("300"),
                vessel_name="MV Alpha",
                imo_number="1234567",
                mmsi="7777777",
                origin_port="Paradip",
                destination_port="Plant One",
                planned_eta=now + timedelta(days=2),
                current_eta=now + timedelta(days=3),
                eta_confidence=Decimal("75"),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="manual_upload",
                latest_update_at=now - timedelta(days=5),
            ),
            Shipment(
                tenant_id=tenant_b.id,
                shipment_id="SHIP-B",
                material_id=material_b.id,
                plant_id=plant_b.id,
                supplier_name="Supplier B",
                quantity_mt=Decimal("500"),
                vessel_name="MV Beta",
                imo_number="7654321",
                mmsi="8888888",
                origin_port="Vizag",
                destination_port="Plant B",
                planned_eta=now + timedelta(days=1),
                current_eta=now + timedelta(days=1),
                eta_confidence=Decimal("85"),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="manual_upload",
                latest_update_at=now - timedelta(hours=2),
            ),
        ]
    )
    db.flush()

    db.add_all(
            [
                ExceptionCase(
                    tenant_id=tenant_a.id,
                    type=ExceptionType.STOCKOUT_RISK,
                severity=ExceptionSeverity.CRITICAL,
                status=ExceptionStatus.OPEN,
                title="Coal shortage at Plant One",
                summary="[trigger_source:stock_cover_critical] Cover is below threshold.",
                linked_plant_id=plant_a.id,
                linked_material_id=material_a.id,
                triggered_at=now - timedelta(hours=2),
                due_at=now + timedelta(days=1),
                next_action="Validate stock and expedite inbound movements.",
                ),
                ExceptionCase(
                    tenant_id=tenant_b.id,
                    type=ExceptionType.STOCKOUT_RISK,
                severity=ExceptionSeverity.HIGH,
                status=ExceptionStatus.OPEN,
                title="Tenant B Exception",
                summary="[trigger_source:stock_cover_warning] Tenant B warning.",
                linked_plant_id=plant_b.id,
                linked_material_id=material_b.id,
                triggered_at=now - timedelta(hours=1),
                due_at=now + timedelta(days=1),
                next_action="Review tenant B.",
            ),
            UploadedFile(
                tenant_id=tenant_a.id,
                original_filename="stock.csv",
                storage_uri="/tmp/stock.csv",
                content_type="text/csv",
                file_size_bytes=128,
                checksum_sha256="abc123",
                uploaded_by_user_id=admin.id,
                status="processed",
            ),
        ]
    )
    db.flush()

    uploaded_file = db.query(UploadedFile).filter(UploadedFile.tenant_id == tenant_a.id).one()
    db.add(
        IngestionJob(
            tenant_id=tenant_a.id,
            uploaded_file_id=uploaded_file.id,
            source_type="stock",
            status="completed",
            started_at=now - timedelta(minutes=5),
            completed_at=now - timedelta(minutes=1),
            records_total=5,
            records_succeeded=5,
            records_failed=0,
        )
    )
    db.add(
        AuditLog(
            tenant_id=tenant_a.id,
            actor_user_id=admin.id,
            action="exception.evaluation_triggered",
            entity_type="exception_evaluation",
            entity_id=tenant_a.slug,
            metadata_json="{}",
        )
    )
    db.commit()


def login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def tenant_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": "pilot-tenant"}
