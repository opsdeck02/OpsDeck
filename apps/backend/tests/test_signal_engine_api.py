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
    Material,
    Plant,
    Role,
    Shipment,
    StockSnapshot,
    Tenant,
    TenantMembership,
    User,
)
from app.models.enums import (
    OperationalEventCategory,
    OperationalEventSourceType,
    OperationalEventType,
    ShipmentState,
)
from app.modules.auth.constants import LOGISTICS_USER
from app.modules.auth.security import hash_password
from app.modules.operational_events.schemas import OperationalEventCreate
from app.modules.operational_events.service import create_operational_event


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        seed_signal_engine_data(db)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
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


def test_risks_endpoint_returns_explainable_risk_candidates(client: TestClient) -> None:
    response = client.get("/api/v1/signal-engine/risks", headers=auth_headers(client))

    assert response.status_code == 200
    risks = response.json()
    assert any(risk["risk_type"] == "days_of_cover_breach" for risk in risks)
    assert all(risk["explainability"] is not None for risk in risks)


def test_risk_workspace_returns_selected_risk_plus_explainability(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["empty"] is False
    assert body["selected_risk"]["severity"] == "critical"
    assert body["explainability"]["primary_driver"] in {
        "inventory_continuity",
        "shipment_continuity",
    }


def test_risk_workspace_selects_highest_priority_risk_deterministically(
    client: TestClient,
) -> None:
    first = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )
    second = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_risk = first.json()["selected_risk"]
    second_risk = second.json()["selected_risk"]
    assert first_risk["risk_type"] == second_risk["risk_type"]
    assert first_risk["severity"] == second_risk["severity"] == "critical"


def test_risk_workspace_includes_exposure(client: TestClient) -> None:
    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert response.status_code == 200
    exposure = response.json()["exposure"]
    assert exposure["plant_reference"] == "P1"
    assert exposure["material_reference"] == "M1"
    assert exposure["exposure_level"] == "immediate"


def test_risk_workspace_includes_timeline_window(client: TestClient) -> None:
    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={
            "plant_reference": "P1",
            "material_reference": "M1",
            "timeline_limit": 0,
            "timeline_offset": 0,
        },
    )

    assert response.status_code == 200
    timeline = response.json()["timeline"]
    assert timeline["items"] == []
    assert timeline["limit"] == 0
    assert timeline["offset"] == 0
    assert timeline["total"] == 1


def test_risk_workspace_includes_context_graph(client: TestClient) -> None:
    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert response.status_code == 200
    graph = response.json()["context_graph"]
    assert graph["nodes"]
    assert graph["summary"]["inventory_continuity"]["plant_reference"] == "P1"


def test_risk_workspace_includes_inventory_continuity_for_context(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert response.status_code == 200
    inventory = response.json()["inventory_continuity"]
    assert inventory[0]["usable_quantity"] == "20.00"
    assert inventory[0]["days_of_cover"] == "2.00"


def test_risk_workspace_includes_shipment_continuity_for_shipment_context(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"shipment_reference": "SHIP-1"},
    )

    assert response.status_code == 200
    shipments = response.json()["shipment_continuity"]
    assert shipments[0]["shipment_reference"] == "SHIP-1"
    assert shipments[0]["status"] == "degraded"


def test_risk_workspace_includes_trust_summary(client: TestClient) -> None:
    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert response.status_code == 200
    trust = response.json()["trust_summary"]
    assert "lowest_confidence_score" in trust
    assert "worst_freshness_status" in trust
    assert "warnings" in trust


def test_risk_workspace_returns_empty_response_when_no_candidate_matches(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"risk_type": "not_a_real_risk"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["empty"] is True
    assert body["selected_risk"] is None
    assert body["timeline"]["total"] == 0


def test_risk_workspace_tenant_isolation_is_enforced(client: TestClient) -> None:
    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P2", "material_reference": "M2"},
    )

    assert response.status_code == 200
    assert response.json()["empty"] is True

    cross_tenant = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers={**auth_headers(client), "X-Tenant-Slug": "tenant-b"},
    )
    assert cross_tenant.status_code == 404


def test_exposure_endpoint_returns_exposure_mappings(client: TestClient) -> None:
    response = client.get(
        "/api/v1/signal-engine/exposure",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body[0]["plant_reference"] == "P1"
    assert body[0]["material_reference"] == "M1"
    assert body[0]["exposure_level"] in {"immediate", "near_term", "watch"}


def test_timeline_endpoint_returns_continuity_entries(client: TestClient) -> None:
    response = client.get(
        "/api/v1/signal-engine/timeline",
        headers=auth_headers(client),
        params={"event_category": "inventory"},
    )

    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 1
    assert entries[0]["event_type"] == "inventory_stock_updated"
    assert entries[0]["confidence_score"] is not None
    assert entries[0]["freshness_status"] == "fresh"


def test_context_graph_endpoint_returns_nodes_edges_and_summary(client: TestClient) -> None:
    response = client.get(
        "/api/v1/signal-engine/context-graph",
        headers=auth_headers(client),
        params={"shipment_reference": "SHIP-1"},
    )

    assert response.status_code == 200
    graph = response.json()
    assert graph["nodes"]
    assert graph["edges"]
    assert graph["summary"]["shipment_continuity"]["shipment_reference"] == "SHIP-1"


def test_inventory_continuity_endpoint_returns_usable_quantity_and_doc(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/signal-engine/inventory-continuity",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert response.status_code == 200
    item = response.json()[0]
    assert item["usable_quantity"] == "20.00"
    assert item["days_of_cover"] == "2.00"


def test_shipment_continuity_endpoint_returns_continuity_status(client: TestClient) -> None:
    response = client.get(
        "/api/v1/signal-engine/shipment-continuity",
        headers=auth_headers(client),
        params={"shipment_reference": "SHIP-1"},
    )

    assert response.status_code == 200
    item = response.json()[0]
    assert item["shipment_reference"] == "SHIP-1"
    assert item["status"] == "degraded"


def test_filters_work_for_context_fields(client: TestClient) -> None:
    response = client.get(
        "/api/v1/signal-engine/risks",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1", "severity": "critical"},
    )

    assert response.status_code == 200
    risks = response.json()
    assert risks
    assert all(risk["plant_reference"] == "P1" for risk in risks)
    assert all(risk["material_reference"] == "M1" for risk in risks)
    assert all(risk["severity"] == "critical" for risk in risks)


def test_signal_engine_tenant_isolation_is_enforced(client: TestClient) -> None:
    response = client.get(
        "/api/v1/signal-engine/inventory-continuity",
        headers=auth_headers(client),
        params={"plant_reference": "P2", "material_reference": "M2"},
    )

    assert response.status_code == 200
    assert response.json() == []

    cross_tenant = client.get(
        "/api/v1/signal-engine/risks",
        headers={**auth_headers(client), "X-Tenant-Slug": "tenant-b"},
    )
    assert cross_tenant.status_code == 404


def test_signal_engine_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/signal-engine/risks")

    assert response.status_code == 401


NOW = datetime(2026, 5, 9, 12, tzinfo=UTC)


def seed_signal_engine_data(db: Session) -> None:
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    role = Role(name=LOGISTICS_USER, description="Logistics")
    db.add_all([tenant_a, tenant_b, role])
    db.flush()

    user = User(
        email="ops@test.local",
        full_name="Ops User",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        TenantMembership(
            tenant_id=tenant_a.id,
            user_id=user.id,
            role_id=role.id,
            is_active=True,
        )
    )

    plant_a = Plant(tenant_id=tenant_a.id, code="P1", name="Plant 1", location="East")
    material_a = Material(
        tenant_id=tenant_a.id,
        code="M1",
        name="Material 1",
        category="raw",
        uom="MT",
    )
    plant_b = Plant(tenant_id=tenant_b.id, code="P2", name="Plant 2", location="West")
    material_b = Material(
        tenant_id=tenant_b.id,
        code="M2",
        name="Material 2",
        category="raw",
        uom="MT",
    )
    db.add_all([plant_a, material_a, plant_b, material_b])
    db.flush()

    db.add_all(
        [
            StockSnapshot(
                tenant_id=tenant_a.id,
                plant_id=plant_a.id,
                material_id=material_a.id,
                on_hand_mt=Decimal("20"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("20"),
                daily_consumption_mt=Decimal("10"),
                snapshot_time=NOW,
            ),
            StockSnapshot(
                tenant_id=tenant_b.id,
                plant_id=plant_b.id,
                material_id=material_b.id,
                on_hand_mt=Decimal("10"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("10"),
                daily_consumption_mt=Decimal("10"),
                snapshot_time=NOW,
            ),
            Shipment(
                tenant_id=tenant_a.id,
                shipment_id="SHIP-1",
                material_id=material_a.id,
                plant_id=plant_a.id,
                supplier_name="Supplier 1",
                quantity_mt=Decimal("50"),
                planned_eta=NOW + timedelta(days=1),
                current_eta=NOW + timedelta(days=4),
                latest_eta=NOW + timedelta(days=1),
                current_milestone="in_transit",
                last_tracking_update_at=NOW - timedelta(hours=8),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="manual_upload",
                latest_update_at=NOW - timedelta(hours=8),
            ),
        ]
    )
    create_operational_event(
        db,
        OperationalEventCreate(
            tenant_id=tenant_a.id,
            event_type=OperationalEventType.INVENTORY_STOCK_UPDATED,
            event_category=OperationalEventCategory.INVENTORY,
            source_type=OperationalEventSourceType.FILE_INGESTION,
            source_reference="file_ingestion",
            occurred_at=NOW,
            detected_at=NOW,
            plant_reference=plant_a.code,
            material_reference=material_a.code,
            quantity_value=Decimal("20"),
            quantity_unit="MT",
            new_value={"available_to_consume_mt": "20"},
        ),
    )
    create_operational_event(
        db,
        OperationalEventCreate(
            tenant_id=tenant_b.id,
            event_type=OperationalEventType.INVENTORY_STOCK_UPDATED,
            event_category=OperationalEventCategory.INVENTORY,
            source_type=OperationalEventSourceType.FILE_INGESTION,
            source_reference="file_ingestion",
            occurred_at=NOW,
            detected_at=NOW,
            plant_reference=plant_b.code,
            material_reference=material_b.code,
            quantity_value=Decimal("10"),
            quantity_unit="MT",
            new_value={"available_to_consume_mt": "10"},
        ),
    )
    db.commit()


def auth_headers(client: TestClient) -> dict[str, str]:
    token = login(client)
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": "tenant-a"}


def login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ops@test.local", "password": "Password123!"},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])
