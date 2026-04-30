from __future__ import annotations

import io
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import (
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
from app.modules.auth.constants import LOGISTICS_USER
from app.modules.auth.security import hash_password


@pytest.fixture()
def client_and_session() -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        seed_ingestion_test_data(db)

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


def seed_ingestion_test_data(db: Session) -> None:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    role = Role(name=LOGISTICS_USER, description="Logistics")
    db.add_all([tenant, role])
    db.flush()
    user = User(
        email="logistics@test.local",
        full_name="Logistics User",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    plant = Plant(tenant_id=tenant.id, code="JAM", name="Jamshedpur", location="Jharkhand")
    material = Material(
        tenant_id=tenant.id,
        code="COKING_COAL",
        name="Coking coal",
        category="coal",
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


def login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "logistics@test.local", "password": "Password123!"},
    )
    assert response.status_code == 200, response.json()
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": "tenant-a"}


def upload_csv(client: TestClient, headers: dict[str, str], file_type: str, csv_body: str):
    return client.post(
        "/api/v1/ingestion/uploads",
        headers=headers,
        data={"file_type": file_type},
        files={"file": ("upload.csv", csv_body.encode(), "text/csv")},
    )


def upload_xlsx(client: TestClient, headers: dict[str, str], file_type: str, content: bytes):
    return client.post(
        "/api/v1/ingestion/uploads",
        headers=headers,
        data={"file_type": file_type},
        files={
            "file": (
                "stock_snapshot.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


def test_valid_shipment_upload(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, SessionLocal = client_and_session
    response = upload_csv(client, login(client), "shipment", shipment_csv("SHP-001"))

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["rows_received"] == 1
    assert body["rows_accepted"] == 1
    assert body["summary_counts"]["created"] == 1

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Shipment)) == 1


def test_valid_stock_upload(client_and_session: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, SessionLocal = client_and_session
    response = upload_csv(
        client,
        login(client),
        "stock",
        "\n".join(
            [
                "plant_code,material_code,on_hand_mt,quality_held_mt,available_to_consume_mt,daily_consumption_mt,snapshot_time",
                "JAM,COKING_COAL,10000,1000,9000,500,2026-04-15T08:00:00Z",
            ]
        ),
    )

    assert response.status_code == 200
    assert response.json()["summary_counts"]["created"] == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(StockSnapshot)) == 1


def test_stock_xlsx_detects_headers_on_row_three(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, SessionLocal = client_and_session

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Stock snapshot export"])
    sheet.append(["Generated from customer workbook"])
    sheet.append(
        [
            "last_updated_at",
            "plant_code",
            "material_code",
            "material_name",
            "current_stock_tons",
            "available_unrestricted_tons",
            "blocked_stock_tons",
            "in_transit_open_tons",
            "daily_consumption_tons",
            "days_to_line_stop",
            "risk_status",
            "next_inbound_eta_days",
        ]
    )
    sheet.append(
        [
            "2026-04-15T08:00:00Z",
            "JAM",
            "COKING_COAL",
            "Coking coal",
            10000,
            9000,
            1000,
            2500,
            500,
            18,
            "safe",
            4,
        ]
    )
    output = io.BytesIO()
    workbook.save(output)

    response = upload_xlsx(client, login(client), "stock", output.getvalue())

    assert response.status_code == 200, response.json()
    assert response.json()["rows_accepted"] == 1
    with SessionLocal() as db:
        snapshot = db.scalar(select(StockSnapshot))
        assert snapshot is not None
        assert str(snapshot.on_hand_mt) == "10000.000"
        assert str(snapshot.available_to_consume_mt) == "9000.000"
        assert str(snapshot.quality_held_mt) == "1000.000"


def test_invalid_stock_upload_rejects_zero_daily_consumption(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, SessionLocal = client_and_session
    response = upload_csv(
        client,
        login(client),
        "stock",
        "\n".join(
            [
                "plant_code,material_code,on_hand_mt,quality_held_mt,available_to_consume_mt,daily_consumption_mt,snapshot_time",
                "JAM,COKING_COAL,10000,1000,9000,0,2026-04-15T08:00:00Z",
            ]
        ),
    )

    assert response.status_code == 400
    assert "daily_consumption_mt must be greater than zero" in str(response.json())
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(StockSnapshot)) == 0


def test_threshold_upload(client_and_session: tuple[TestClient, sessionmaker[Session]]) -> None:
    client, SessionLocal = client_and_session
    response = upload_csv(
        client,
        login(client),
        "threshold",
        "\n".join(
            [
                "plant_code,material_code,threshold_days,warning_days",
                "JAM,COKING_COAL,7,10",
            ]
        ),
    )

    assert response.status_code == 200
    assert response.json()["summary_counts"]["created"] == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PlantMaterialThreshold)) == 1


def test_duplicate_shipment_reupload_is_idempotent(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, SessionLocal = client_and_session
    headers = login(client)

    first_response = upload_csv(client, headers, "shipment", shipment_csv("SHP-REPEAT"))
    second_response = upload_csv(client, headers, "shipment", shipment_csv("SHP-REPEAT"))

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["summary_counts"]["unchanged"] == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Shipment)) == 1


def test_shipment_upload_accepts_dispatched_state_and_date_only_eta(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, SessionLocal = client_and_session
    response = upload_csv(
        client,
        login(client),
        "shipment",
        "\n".join(
            [
                "shipment_id,plant_code,material_code,supplier_name,quantity_mt,planned_eta,current_eta,current_state,latest_update_at",
                "SHP-DISPATCHED,JAM,COKING_COAL,Supplier A,74000,2026-04-20,2026-04-21,dispatched,2026-04-15 09:00:00",
            ]
        ),
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        shipment = db.scalar(select(Shipment).where(Shipment.shipment_id == "SHP-DISPATCHED"))
        assert shipment is not None
        assert shipment.current_state == "in_transit"


def test_shipment_upload_can_derive_current_eta_from_delay_days(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, SessionLocal = client_and_session
    response = upload_csv(
        client,
        login(client),
        "shipment",
        "\n".join(
            [
                "shipment_id,plant_code,material_code,supplier_name,quantity_mt,planned_eta,delay_days,current_state,latest_update_at",
                "SHP-DELAY-DAYS,JAM,COKING_COAL,Supplier A,74000,2026-04-20T08:00:00Z,2.5,in_transit,2026-04-15T09:00:00Z",
            ]
        ),
    )

    assert response.status_code == 200, response.json()
    with SessionLocal() as db:
        shipment = db.scalar(select(Shipment).where(Shipment.shipment_id == "SHP-DELAY-DAYS"))
        assert shipment is not None
        assert shipment.current_eta.isoformat() == "2026-04-22T20:00:00"


def test_delete_uploaded_data_clears_tenant_ingestion_artifacts(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, SessionLocal = client_and_session
    headers = login(client)

    shipment_response = upload_csv(client, headers, "shipment", shipment_csv("SHP-CLEAR"))
    stock_response = upload_csv(
        client,
        headers,
        "stock",
        "\n".join(
            [
                "plant_code,material_code,on_hand_mt,quality_held_mt,available_to_consume_mt,daily_consumption_mt,snapshot_time",
                "JAM,COKING_COAL,10000,1000,9000,500,2026-04-15T08:00:00Z",
            ]
        ),
    )
    threshold_response = upload_csv(
        client,
        headers,
        "threshold",
        "\n".join(
            [
                "plant_code,material_code,threshold_days,warning_days",
                "JAM,COKING_COAL,7,10",
            ]
        ),
    )

    assert shipment_response.status_code == 200
    assert stock_response.status_code == 200
    assert threshold_response.status_code == 200

    delete_response = client.delete("/api/v1/ingestion/uploads", headers=headers)
    assert delete_response.status_code == 200
    body = delete_response.json()
    assert body["shipments"] == 1
    assert body["stock_snapshots"] == 1
    assert body["thresholds"] == 1
    assert body["ingestion_jobs"] == 3
    assert body["uploaded_files"] == 3

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Shipment)) == 0
        assert db.scalar(select(func.count()).select_from(StockSnapshot)) == 0
        assert db.scalar(select(func.count()).select_from(PlantMaterialThreshold)) == 0
        assert db.scalar(select(func.count()).select_from(IngestionJob)) == 0
        assert db.scalar(select(func.count()).select_from(UploadedFile)) == 0


def test_mapping_preview_and_manual_override_support_nonstandard_headers(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, SessionLocal = client_and_session
    headers = login(client)
    csv_body = "\n".join(
        [
            "OneDrive shipment export",
            "shipment reference,plant location,material name,vendor,qty,eta original,eta latest,status now,last updated",
            "SHP-MAP,JAM,COKING_COAL,Supplier A,74000,2026-04-20T08:00:00Z,2026-04-21T08:00:00Z,in_transit,2026-04-15T09:00:00Z",
        ]
    )

    preview_response = client.post(
        "/api/v1/ingestion/mapping-preview",
        headers=headers,
        data={"file_type": "shipment"},
        files={"file": ("mapping.csv", csv_body.encode(), "text/csv")},
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert "shipment_id" in preview["required_fields"]
    assert preview["headers"][0] == "shipment reference"
    suggested = {
        item["source_header"]: item["suggested_field"]
        for item in preview["suggestions"]
    }
    assert suggested["shipment reference"] == "shipment_id"
    assert suggested["vendor"] == "supplier_name"

    upload_response = client.post(
        "/api/v1/ingestion/uploads",
        headers=headers,
        data={
          "file_type": "shipment",
            "mapping_overrides": '{"plant location":"plant_code","material name":"material_code","eta original":"planned_eta","eta latest":"current_eta","status now":"current_state"}',
        },
        files={"file": ("mapping.csv", csv_body.encode(), "text/csv")},
    )
    assert upload_response.status_code == 200
    with SessionLocal() as db:
        shipment = db.scalar(select(Shipment))
        assert shipment is not None
        assert shipment.source_of_truth == "manual_upload"


def shipment_csv(shipment_id: str) -> str:
    header = (
        "shipment_id,plant_code,material_code,supplier_name,quantity_mt,"
        "planned_eta,current_eta,current_state,latest_update_at"
    )
    row = (
        f"{shipment_id},JAM,COKING_COAL,Supplier A,74000,"
        "2026-04-20T08:00:00Z,2026-04-21T08:00:00Z,"
        "in_transit,2026-04-15T09:00:00Z"
    )
    return "\n".join(
        [
            header,
            row,
        ]
    )
