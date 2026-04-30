from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import (
    ExceptionCase,
    InlandMovement,
    Material,
    MicrosoftConnection,
    MicrosoftDataSource,
    Plant,
    PlantMaterialThreshold,
    PortEvent,
    Role,
    Shipment,
    StockSnapshot,
    Tenant,
    TenantMembership,
    User,
)
from app.models.enums import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ShipmentState,
)
from app.modules.auth.constants import LOGISTICS_USER
from app.modules.auth.security import hash_password


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session() as db:
        seed_dashboard_data(db)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
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


def seed_dashboard_data(db: Session) -> None:
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    role = Role(name=LOGISTICS_USER, description="Logistics")
    db.add_all([tenant_a, tenant_b, role])
    db.flush()

    owner = User(
        email="owner@test.local",
        full_name="Owner User",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    viewer = User(
        email="viewer@test.local",
        full_name="Viewer User",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    db.add_all([owner, viewer])
    db.flush()
    db.add_all(
        [
            TenantMembership(
                tenant_id=tenant_a.id,
                user_id=owner.id,
                role_id=role.id,
                is_active=True,
            ),
            TenantMembership(
                tenant_id=tenant_a.id,
                user_id=viewer.id,
                role_id=role.id,
                is_active=True,
            ),
        ]
    )

    plant1 = Plant(tenant_id=tenant_a.id, code="P1", name="Plant One", location="India")
    plant2 = Plant(tenant_id=tenant_a.id, code="P2", name="Plant Two", location="India")
    plant_b = Plant(tenant_id=tenant_b.id, code="PB", name="Plant B", location="India")
    material1 = Material(
        tenant_id=tenant_a.id,
        code="M1",
        name="Coal A",
        category="coal",
        uom="MT",
    )
    material2 = Material(
        tenant_id=tenant_a.id,
        code="M2",
        name="Coal B",
        category="coal",
        uom="MT",
    )
    material_b = Material(
        tenant_id=tenant_b.id,
        code="MB",
        name="Coal B Tenant",
        category="coal",
        uom="MT",
    )
    db.add_all([plant1, plant2, plant_b, material1, material2, material_b])
    db.flush()

    now = datetime.now(UTC)
    db.add_all(
        [
            PlantMaterialThreshold(
                tenant_id=tenant_a.id,
                plant_id=plant1.id,
                material_id=material1.id,
                threshold_days=Decimal("5"),
                warning_days=Decimal("8"),
            ),
            PlantMaterialThreshold(
                tenant_id=tenant_a.id,
                plant_id=plant2.id,
                material_id=material2.id,
                threshold_days=Decimal("5"),
                warning_days=Decimal("8"),
            ),
            StockSnapshot(
                tenant_id=tenant_a.id,
                plant_id=plant1.id,
                material_id=material1.id,
                on_hand_mt=Decimal("200"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("200"),
                daily_consumption_mt=Decimal("100"),
                snapshot_time=now - timedelta(hours=2),
            ),
            StockSnapshot(
                tenant_id=tenant_a.id,
                plant_id=plant2.id,
                material_id=material2.id,
                on_hand_mt=Decimal("650"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("650"),
                daily_consumption_mt=Decimal("100"),
                snapshot_time=now - timedelta(hours=5),
            ),
            StockSnapshot(
                tenant_id=tenant_b.id,
                plant_id=plant_b.id,
                material_id=material_b.id,
                on_hand_mt=Decimal("100"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("100"),
                daily_consumption_mt=Decimal("50"),
                snapshot_time=now - timedelta(hours=1),
            ),
        ]
    )
    db.add_all(
        [
            Shipment(
                tenant_id=tenant_a.id,
                shipment_id="SHIP-LOW",
                material_id=material1.id,
                plant_id=plant1.id,
                supplier_name="Supplier A",
                quantity_mt=Decimal("300"),
                vessel_name="MV Alpha",
                imo_number="1234567",
                mmsi="7777777",
                origin_port="Port",
                destination_port="Port",
                planned_eta=now + timedelta(days=2),
                current_eta=now + timedelta(days=2),
                eta_confidence=Decimal("70"),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="manual_upload",
                latest_update_at=now - timedelta(days=4),
            ),
            Shipment(
                tenant_id=tenant_a.id,
                shipment_id="SHIP-DELAY",
                material_id=material2.id,
                plant_id=plant2.id,
                supplier_name="Supplier B",
                quantity_mt=Decimal("400"),
                vessel_name=None,
                imo_number=None,
                mmsi=None,
                origin_port="Paradip",
                destination_port="Plant Two",
                planned_eta=now - timedelta(hours=6),
                current_eta=now + timedelta(hours=6),
                eta_confidence=Decimal("80"),
                current_state=ShipmentState.INLAND_TRANSIT,
                source_of_truth="manual_upload",
                latest_update_at=now - timedelta(hours=3),
            ),
            Shipment(
                tenant_id=tenant_b.id,
                shipment_id="SHIP-B",
                material_id=material_b.id,
                plant_id=plant_b.id,
                supplier_name="Supplier Z",
                quantity_mt=Decimal("500"),
                vessel_name="MV Other",
                imo_number=None,
                mmsi=None,
                origin_port="Port",
                destination_port="Port",
                planned_eta=now + timedelta(days=1),
                current_eta=now + timedelta(days=1),
                eta_confidence=Decimal("90"),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="manual_upload",
                latest_update_at=now - timedelta(hours=1),
            ),
        ]
    )
    db.flush()

    delayed = db.query(Shipment).filter(Shipment.shipment_id == "SHIP-DELAY").one()
    db.add(
        InlandMovement(
            tenant_id=tenant_a.id,
            shipment_id=delayed.id,
            mode="rail",
            carrier_name="Rail Carrier",
            origin_location="Paradip",
            destination_location="Plant Two",
            planned_departure_at=now - timedelta(days=1),
            planned_arrival_at=now - timedelta(hours=12),
            actual_departure_at=now - timedelta(days=1),
            actual_arrival_at=None,
            current_state="en_route",
        )
    )
    low = db.query(Shipment).filter(Shipment.shipment_id == "SHIP-LOW").one()
    db.add(
        PortEvent(
            tenant_id=tenant_a.id,
            shipment_id=low.id,
            berth_status="waiting",
            waiting_days=Decimal("3"),
            discharge_started_at=None,
            discharge_rate_mt_per_day=None,
            estimated_demurrage_exposure=Decimal("9000"),
            updated_at=now - timedelta(days=4),
        )
    )
    db.add_all(
        [
            ExceptionCase(
                tenant_id=tenant_a.id,
                type=ExceptionType.STOCKOUT_RISK,
                severity=ExceptionSeverity.CRITICAL,
                status=ExceptionStatus.OPEN,
                title="Critical stock risk",
                summary="[trigger_source:stock_cover_critical] Critical stock risk",
                linked_plant_id=plant1.id,
                linked_material_id=material1.id,
                owner_user_id=owner.id,
                triggered_at=now - timedelta(hours=1),
                due_at=now + timedelta(hours=4),
                next_action="Escalate supply recovery.",
            ),
            ExceptionCase(
                tenant_id=tenant_a.id,
                type=ExceptionType.ETA_RISK,
                severity=ExceptionSeverity.HIGH,
                status=ExceptionStatus.OPEN,
                title="Unassigned inland delay",
                summary="[trigger_source:inland_delay_risk] Unassigned inland delay",
                linked_shipment_id=delayed.id,
                linked_plant_id=plant2.id,
                linked_material_id=material2.id,
                owner_user_id=None,
                triggered_at=now - timedelta(hours=2),
                due_at=now + timedelta(hours=8),
                next_action="Refresh inland ETA.",
            ),
            ExceptionCase(
                tenant_id=tenant_b.id,
                type=ExceptionType.STOCKOUT_RISK,
                severity=ExceptionSeverity.CRITICAL,
                status=ExceptionStatus.OPEN,
                title="Tenant B hidden exception",
                summary="[trigger_source:stock_cover_critical] Hidden",
                linked_plant_id=plant_b.id,
                linked_material_id=material_b.id,
                triggered_at=now - timedelta(hours=1),
                due_at=now + timedelta(hours=4),
                next_action="Hidden",
            ),
        ]
    )
    connection = MicrosoftConnection(
        tenant_id=tenant_a.id,
        microsoft_user_id="ms-user-1",
        microsoft_tenant_id="ms-tenant-1",
        display_name="Ops Lead",
        email="ops@example.com",
        access_token="encrypted-access",
        refresh_token="encrypted-refresh",
        token_expires_at=now + timedelta(hours=1),
        scope="Files.Read User.Read offline_access",
        connected_at=now - timedelta(hours=2),
        is_active=True,
    )
    db.add(connection)
    db.flush()
    db.add(
        MicrosoftDataSource(
            tenant_id=tenant_a.id,
            microsoft_connection_id=connection.id,
            drive_id="drive-1",
            item_id="stock-item-1",
            file_type="stock",
            sync_frequency_minutes=60,
            last_successful_sync_at=now - timedelta(minutes=15),
            last_sync_attempted_at=now - timedelta(minutes=15),
            sync_status="success",
            is_active=True,
            display_name="stock_snapshot.xlsx",
        )
    )
    db.commit()


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@test.local", "password": "Password123!"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": "tenant-a"}


def test_correct_aggregation_of_kpis(client: TestClient) -> None:
    headers = auth_headers(client)
    response = client.get("/api/v1/dashboard/executive", headers=headers)
    assert response.status_code == 200
    body = response.json()
    stock = client.get("/api/v1/stock/cover", headers=headers).json()
    expected_total = sum(
        Decimal(row["calculation"]["estimated_value_at_risk"])
        for row in stock["rows"]
        if row["calculation"]["status"] == "critical"
        and row["calculation"]["estimated_value_at_risk"] is not None
    )
    assert body["kpis"]["tracked_combinations"] == 2
    assert body["kpis"]["open_exceptions"] == 2
    assert body["kpis"]["unassigned_exceptions"] == 1
    assert Decimal(body["kpis"]["total_estimated_value_at_risk"]) == expected_total


def test_microsoft_data_sources_count_as_automated_freshness(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/executive", headers=auth_headers(client))
    assert response.status_code == 200
    freshness = response.json()["automated_data_freshness"]
    assert freshness is not None
    assert freshness["last_sync_summary"]["last_sync_status"] == "success"
    assert freshness["data_freshness_status"] == "fresh"


def test_correct_filtering_of_top_risks(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/executive", headers=auth_headers(client))
    body = response.json()
    assert len(body["top_risks"]) >= 1
    assert body["top_risks"][0]["status"] == "critical"
    assert body["top_risks"][0]["plant_name"] == "Plant One"
    assert body["top_risks"][0]["urgency_band"] == "next_72h"
    assert Decimal(body["top_risks"][0]["estimated_value_at_risk"]) > Decimal("0")
    assert body["top_risks"][0]["value_per_mt_used"] is not None
    assert body["top_risks"][0]["criticality_multiplier_used"] is not None
    assert body["top_risks"][0]["recommended_action_text"] is not None
    assert body["top_risks"][0]["owner_role_recommended"] is not None
    assert body["top_risks"][0]["action_deadline_hours"] is not None


def test_exception_summary_accuracy(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/executive", headers=auth_headers(client))
    body = response.json()
    assert body["critical_open_exceptions"][0]["title"] == "Critical stock risk"
    assert body["unassigned_exceptions"][0]["title"] == "Unassigned inland delay"


def test_tenant_isolation(client: TestClient) -> None:
    headers = auth_headers(client)
    response = client.get("/api/v1/dashboard/executive", headers=headers)
    body = response.json()
    assert all(item["plant_name"] != "Plant B" for item in body["top_risks"])
    titles = {item["title"] for item in body["critical_open_exceptions"]}
    assert "Tenant B hidden exception" not in titles
    assert all(
        item["estimated_value_at_risk"] is None or Decimal(item["estimated_value_at_risk"]) >= Decimal("0")
        for item in body["top_risks"]
    )
    assert all(item["owner_role_recommended"] is not None for item in body["top_risks"])


def test_attention_items_surface_recommended_action_and_owner(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/executive", headers=auth_headers(client))
    body = response.json()
    stock_items = [item for item in body["needs_attention"] if item["kind"] == "stock_risk"]
    assert stock_items
    assert stock_items[0]["recommended_next_step"] is not None
    assert stock_items[0]["owner_role_recommended"] is not None
    assert stock_items[0]["action_deadline_hours"] is not None
