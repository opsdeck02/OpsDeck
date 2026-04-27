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
    Plant,
    PlantMaterialThreshold,
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
from app.modules.auth.constants import LOGISTICS_USER, PLANNER_USER
from app.modules.auth.security import hash_password


@pytest.fixture()
def app_setup() -> Generator[tuple[TestClient, sessionmaker], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        seed_exception_data(db)

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


def seed_exception_data(db: Session) -> None:
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    logistics_role = Role(name=LOGISTICS_USER, description="Logistics")
    planner_role = Role(name=PLANNER_USER, description="Planner")
    db.add_all([tenant_a, tenant_b, logistics_role, planner_role])
    db.flush()

    ops_user = User(
        email="ops@test.local",
        full_name="Ops User",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    planner_user = User(
        email="planner@test.local",
        full_name="Planner User",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    other_tenant_user = User(
        email="other@test.local",
        full_name="Other Tenant User",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    db.add_all([ops_user, planner_user, other_tenant_user])
    db.flush()

    db.add_all(
        [
            TenantMembership(
                tenant_id=tenant_a.id,
                user_id=ops_user.id,
                role_id=logistics_role.id,
                is_active=True,
            ),
            TenantMembership(
                tenant_id=tenant_a.id,
                user_id=planner_user.id,
                role_id=planner_role.id,
                is_active=True,
            ),
            TenantMembership(
                tenant_id=tenant_b.id,
                user_id=other_tenant_user.id,
                role_id=logistics_role.id,
                is_active=True,
            ),
        ]
    )

    plant_critical = Plant(tenant_id=tenant_a.id, code="P1", name="Plant One", location="India")
    plant_warning = Plant(tenant_id=tenant_a.id, code="P2", name="Plant Two", location="India")
    plant_safe = Plant(tenant_id=tenant_a.id, code="P3", name="Plant Three", location="India")
    plant_b = Plant(tenant_id=tenant_b.id, code="PB", name="Tenant B Plant", location="India")
    material_critical = Material(
        tenant_id=tenant_a.id,
        code="M1",
        name="Coal A",
        category="coal",
        uom="MT",
    )
    material_warning = Material(
        tenant_id=tenant_a.id,
        code="M2",
        name="Coal B",
        category="coal",
        uom="MT",
    )
    material_safe = Material(
        tenant_id=tenant_a.id,
        code="M3",
        name="Coal C",
        category="coal",
        uom="MT",
    )
    material_b = Material(
        tenant_id=tenant_b.id,
        code="MB",
        name="Tenant B Coal",
        category="coal",
        uom="MT",
    )
    db.add_all(
        [
            plant_critical,
            plant_warning,
            plant_safe,
            plant_b,
            material_critical,
            material_warning,
            material_safe,
            material_b,
        ]
    )
    db.flush()

    db.add_all(
        [
            PlantMaterialThreshold(
                tenant_id=tenant_a.id,
                plant_id=plant_critical.id,
                material_id=material_critical.id,
                threshold_days=Decimal("5"),
                warning_days=Decimal("8"),
            ),
            PlantMaterialThreshold(
                tenant_id=tenant_a.id,
                plant_id=plant_warning.id,
                material_id=material_warning.id,
                threshold_days=Decimal("5"),
                warning_days=Decimal("8"),
            ),
            PlantMaterialThreshold(
                tenant_id=tenant_a.id,
                plant_id=plant_safe.id,
                material_id=material_safe.id,
                threshold_days=Decimal("5"),
                warning_days=Decimal("8"),
            ),
        ]
    )

    now = datetime.now(UTC)
    db.add_all(
        [
            StockSnapshot(
                tenant_id=tenant_a.id,
                plant_id=plant_critical.id,
                material_id=material_critical.id,
                on_hand_mt=Decimal("300"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("300"),
                daily_consumption_mt=Decimal("100"),
                snapshot_time=now - timedelta(hours=2),
            ),
            StockSnapshot(
                tenant_id=tenant_a.id,
                plant_id=plant_warning.id,
                material_id=material_warning.id,
                on_hand_mt=Decimal("650"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("650"),
                daily_consumption_mt=Decimal("100"),
                snapshot_time=now - timedelta(hours=3),
            ),
            StockSnapshot(
                tenant_id=tenant_a.id,
                plant_id=plant_safe.id,
                material_id=material_safe.id,
                on_hand_mt=Decimal("900"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("900"),
                daily_consumption_mt=Decimal("100"),
                snapshot_time=now - timedelta(hours=1),
            ),
            StockSnapshot(
                tenant_id=tenant_b.id,
                plant_id=plant_b.id,
                material_id=material_b.id,
                on_hand_mt=Decimal("200"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("200"),
                daily_consumption_mt=Decimal("100"),
                snapshot_time=now - timedelta(hours=1),
            ),
        ]
    )

    shipment_delay = Shipment(
        tenant_id=tenant_a.id,
        shipment_id="ETA-1",
        material_id=material_safe.id,
        plant_id=plant_safe.id,
        supplier_name="Supplier A",
        quantity_mt=Decimal("1000"),
        vessel_name="MV Alpha",
        imo_number="1111111",
        mmsi="999999999",
        origin_port="Hay Point",
        destination_port="Paradip",
        planned_eta=now + timedelta(days=1),
        current_eta=now + timedelta(days=3),
        eta_confidence=Decimal("80"),
        current_state=ShipmentState.IN_TRANSIT,
        source_of_truth="manual_upload",
        latest_update_at=now - timedelta(hours=6),
    )
    shipment_stale = Shipment(
        tenant_id=tenant_a.id,
        shipment_id="STALE-1",
        material_id=material_safe.id,
        plant_id=plant_safe.id,
        supplier_name="Supplier B",
        quantity_mt=Decimal("500"),
        vessel_name=None,
        imo_number=None,
        mmsi=None,
        origin_port="Paradip",
        destination_port="Plant Three",
        planned_eta=now + timedelta(days=2),
        current_eta=now + timedelta(days=2),
        eta_confidence=Decimal("60"),
        current_state=ShipmentState.IN_TRANSIT,
        source_of_truth="manual_upload",
        latest_update_at=now - timedelta(days=10),
    )
    shipment_inland = Shipment(
        tenant_id=tenant_a.id,
        shipment_id="INLAND-1",
        material_id=material_safe.id,
        plant_id=plant_safe.id,
        supplier_name="Supplier C",
        quantity_mt=Decimal("400"),
        vessel_name=None,
        imo_number=None,
        mmsi=None,
        origin_port="Paradip",
        destination_port="Plant Three",
        planned_eta=now + timedelta(days=1),
        current_eta=now + timedelta(days=1),
        eta_confidence=Decimal("85"),
        current_state=ShipmentState.INLAND_TRANSIT,
        source_of_truth="manual_upload",
        latest_update_at=now - timedelta(hours=2),
    )
    db.add_all([shipment_delay, shipment_stale, shipment_inland])
    db.flush()

    db.add(
        InlandMovement(
            tenant_id=tenant_a.id,
            shipment_id=shipment_inland.id,
            mode="rail",
            carrier_name="Rail Carrier",
            origin_location="Port",
            destination_location="Plant Three",
            planned_departure_at=now - timedelta(days=2),
            planned_arrival_at=now - timedelta(hours=30),
            actual_departure_at=now - timedelta(days=2),
            actual_arrival_at=None,
            current_state="en_route",
        )
    )

    db.add(
        ExceptionCase(
            tenant_id=tenant_b.id,
            type=ExceptionType.STOCKOUT_RISK,
            severity=ExceptionSeverity.CRITICAL,
            status=ExceptionStatus.OPEN,
            title="Tenant B hidden case",
            summary="[trigger_source:stock_cover_critical] Tenant B hidden case",
            linked_plant_id=plant_b.id,
            linked_material_id=material_b.id,
            triggered_at=now - timedelta(hours=1),
            due_at=now + timedelta(hours=4),
            next_action="Hidden",
        )
    )
    db.commit()


def auth_headers(client: TestClient, email: str = "ops@test.local") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": "tenant-a"}


def evaluate(client: TestClient) -> dict:
    response = client.post("/api/v1/exceptions/evaluate", headers=auth_headers(client))
    assert response.status_code == 200
    return response.json()


def list_items(client: TestClient, query: str = "") -> list[dict]:
    response = client.get(f"/api/v1/exceptions{query}", headers=auth_headers(client))
    assert response.status_code == 200
    return response.json()["items"]


def test_stock_critical_exception_creation(app_setup: tuple[TestClient, sessionmaker]) -> None:
    client, _ = app_setup
    evaluate(client)
    critical = next(
        item for item in list_items(client) if item["type"] == "stock_cover_critical"
    )
    assert critical["severity"] == "critical"
    assert critical["linked_plant"]["label"] == "Plant One"


def test_stock_warning_exception_creation(app_setup: tuple[TestClient, sessionmaker]) -> None:
    client, _ = app_setup
    evaluate(client)
    warning = next(item for item in list_items(client) if item["type"] == "stock_cover_warning")
    assert warning["severity"] == "high"
    assert warning["linked_material"]["label"] == "Coal B"


def test_duplicate_detection_idempotent_update_behavior(
    app_setup: tuple[TestClient, sessionmaker],
) -> None:
    client, _ = app_setup
    first = evaluate(client)
    second = evaluate(client)
    items = list_items(client)
    assert first["created"] >= 4
    assert second["created"] == 0
    assert len(items) == first["open_after_evaluation"]


def test_exception_resolution_path_when_condition_clears(
    app_setup: tuple[TestClient, sessionmaker],
) -> None:
    client, testing_session = app_setup
    evaluate(client)

    with testing_session() as db:
        plant = db.query(Plant).filter(Plant.code == "P1").one()
        material = db.query(Material).filter(Material.code == "M1").one()
        db.add(
            StockSnapshot(
                tenant_id=plant.tenant_id,
                plant_id=plant.id,
                material_id=material.id,
                on_hand_mt=Decimal("1600"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("1600"),
                daily_consumption_mt=Decimal("100"),
                snapshot_time=datetime.now(UTC),
            )
        )
        db.commit()

    evaluate(client)
    resolved = next(
        item
        for item in list_items(client, "?status=resolved")
        if item["type"] == "stock_cover_critical"
    )
    assert resolved["status"] == "resolved"


def test_manual_owner_assignment(app_setup: tuple[TestClient, sessionmaker]) -> None:
    client, _ = app_setup
    evaluate(client)
    critical = next(
        item for item in list_items(client) if item["type"] == "stock_cover_critical"
    )
    users = client.get("/api/v1/users", headers=auth_headers(client)).json()
    planner = next(user for user in users if user["email"] == "planner@test.local")
    response = client.patch(
        f"/api/v1/exceptions/{critical['id']}/owner",
        headers=auth_headers(client),
        json={"owner_user_id": planner["id"]},
    )
    assert response.status_code == 200
    assert response.json()["current_owner"]["full_name"] == "Planner User"


def test_manual_resolved_blocked_for_system_generated_exception(
    app_setup: tuple[TestClient, sessionmaker],
) -> None:
    client, _ = app_setup
    evaluate(client)
    critical = next(
        item for item in list_items(client) if item["type"] == "stock_cover_critical"
    )
    response = client.patch(
        f"/api/v1/exceptions/{critical['id']}/status",
        headers=auth_headers(client),
        json={"status": "resolved"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == (
        "System-generated exceptions can only be resolved by fresh data recomputation."
    )


def test_manual_closed_blocked_for_system_generated_exception(
    app_setup: tuple[TestClient, sessionmaker],
) -> None:
    client, _ = app_setup
    evaluate(client)
    critical = next(
        item for item in list_items(client) if item["type"] == "stock_cover_critical"
    )
    response = client.patch(
        f"/api/v1/exceptions/{critical['id']}/status",
        headers=auth_headers(client),
        json={"status": "closed"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == (
        "System-generated exceptions can only be resolved by fresh data recomputation."
    )


def test_open_to_in_progress_allowed_for_system_generated_exception(
    app_setup: tuple[TestClient, sessionmaker],
) -> None:
    client, _ = app_setup
    evaluate(client)
    critical = next(
        item for item in list_items(client) if item["type"] == "stock_cover_critical"
    )
    response = client.patch(
        f"/api/v1/exceptions/{critical['id']}/status",
        headers=auth_headers(client),
        json={"status": "in_progress"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


def test_comment_creation(app_setup: tuple[TestClient, sessionmaker]) -> None:
    client, _ = app_setup
    evaluate(client)
    critical = next(
        item for item in list_items(client) if item["type"] == "stock_cover_critical"
    )
    response = client.post(
        f"/api/v1/exceptions/{critical['id']}/comments",
        headers=auth_headers(client),
        json={"comment": "Calling the plant to confirm consumption draw."},
    )
    assert response.status_code == 200
    detail = client.get(
        f"/api/v1/exceptions/{critical['id']}",
        headers=auth_headers(client),
    )
    assert detail.status_code == 200
    assert len(detail.json()["comments"]) == 1


def test_exception_action_update(app_setup: tuple[TestClient, sessionmaker]) -> None:
    client, _ = app_setup
    evaluate(client)
    critical = next(
        item for item in list_items(client) if item["type"] == "stock_cover_critical"
    )
    response = client.patch(
        f"/api/v1/exceptions/{critical['id']}/action",
        headers=auth_headers(client),
        json={"action_status": "completed"},
    )
    assert response.status_code == 200
    assert response.json()["action_status"] == "completed"
    assert response.json()["action_sla_breach"] is False
    detail = client.get(
        f"/api/v1/exceptions/{critical['id']}",
        headers=auth_headers(client),
    )
    assert detail.status_code == 200
    assert detail.json()["exception"]["status"] == "open"


def test_tenant_isolation_behavior(app_setup: tuple[TestClient, sessionmaker]) -> None:
    client, _ = app_setup
    evaluate(client)
    titles = {item["title"] for item in list_items(client)}
    assert "Tenant B hidden case" not in titles


def test_list_filter_behavior(app_setup: tuple[TestClient, sessionmaker]) -> None:
    client, _ = app_setup
    evaluate(client)
    response = client.get(
        "/api/v1/exceptions?type=shipment_eta_delay&status=open",
        headers=auth_headers(client),
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["linked_shipment"]["label"] == "ETA-1"


def test_counts_unchanged_until_recomputation_resolves_case(
    app_setup: tuple[TestClient, sessionmaker],
) -> None:
    client, _ = app_setup
    evaluate(client)
    before = client.get("/api/v1/exceptions", headers=auth_headers(client)).json()["counts"]
    critical = next(
        item for item in list_items(client) if item["type"] == "stock_cover_critical"
    )
    response = client.patch(
        f"/api/v1/exceptions/{critical['id']}/action",
        headers=auth_headers(client),
        json={"action_status": "completed"},
    )
    assert response.status_code == 200
    after = client.get("/api/v1/exceptions", headers=auth_headers(client)).json()["counts"]
    assert after["open_exceptions"] == before["open_exceptions"]
