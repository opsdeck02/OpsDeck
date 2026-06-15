from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.modules.signal_engine.service as signal_service
from app.api.dependencies import get_db
from app.core.config import settings
from app.db.base import Base
from app.main import app
from app.models import (
    LineStopIncident,
    Material,
    OperationalEvent,
    Plant,
    PlantMaterialThreshold,
    Role,
    Shipment,
    StockSnapshot,
    Supplier,
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
from app.modules.rules.engine import RiskCandidate
from app.modules.signal_engine.candidate_cache import (
    clear_signal_candidate_cache,
    get_cached_signal_candidates,
    invalidate_signal_candidate_cache,
)


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    clear_signal_candidate_cache()
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
        clear_signal_candidate_cache()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def test_risks_endpoint_returns_explainable_risk_candidates(client: TestClient) -> None:
    response = client.get("/api/v1/signal-engine/risks", headers=auth_headers(client))

    assert response.status_code == 200
    risks = response.json()
    assert any(risk["risk_type"] == "days_of_cover_breach" for risk in risks)
    assert all(risk["explainability"] is not None for risk in risks)


def test_material_rollups_return_grouped_material_records(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/signal-engine/material-rollups",
        headers=auth_headers(client),
    )

    assert response.status_code == 200
    rollups = response.json()
    assert rollups
    rollup = rollups[0]
    assert rollup["plant_reference"] == "P1"
    assert rollup["material_reference"] == "M1"
    assert rollup["exception_count"] > 0
    assert rollup["highest_severity"] in {"critical", "high", "medium", "low"}
    assert rollup["risk_types"]
    assert "explainability" not in rollup
    assert "operational_interruption_impact" not in rollup
    assert "operational_recommendations" not in rollup
    assert "configuration_completeness" not in rollup
    assert "operational_trust" not in rollup


def test_material_rollup_counts_and_severity_match_candidates(
    client: TestClient,
) -> None:
    headers = auth_headers(client)
    risks_response = client.get("/api/v1/signal-engine/risks", headers=headers)
    rollups_response = client.get(
        "/api/v1/signal-engine/material-rollups",
        headers=headers,
    )

    assert risks_response.status_code == 200
    assert rollups_response.status_code == 200
    risks = risks_response.json()
    rollups = rollups_response.json()
    grouped: dict[tuple[str | None, str | None], list[dict]] = {}
    for risk in risks:
        key = (risk["plant_reference"], risk["material_reference"])
        grouped.setdefault(key, []).append(risk)

    assert len(rollups) == len(grouped)
    for rollup in rollups:
        key = (rollup["plant_reference"], rollup["material_reference"])
        grouped_risks = grouped[key]
        highest = sorted(grouped_risks, key=risk_priority_for_test)[0]
        assert rollup["exception_count"] == len(grouped_risks)
        assert rollup["highest_severity"] == highest["severity"]
        assert rollup["risk_types"] == sorted({risk["risk_type"] for risk in grouped_risks})


def test_material_rollups_support_plant_filter(client: TestClient) -> None:
    response = client.get(
        "/api/v1/signal-engine/material-rollups",
        headers=auth_headers(client),
        params={"plant_reference": "P1"},
    )

    assert response.status_code == 200
    rollups = response.json()
    assert rollups
    assert all(rollup["plant_reference"] == "P1" for rollup in rollups)


def test_material_rollups_tenant_isolation_is_enforced(client: TestClient) -> None:
    response = client.get(
        "/api/v1/signal-engine/material-rollups",
        headers=auth_headers(client),
        params={"plant_reference": "P2", "material_reference": "M2"},
    )

    assert response.status_code == 200
    assert response.json() == []

    cross_tenant = client.get(
        "/api/v1/signal-engine/material-rollups",
        headers={**auth_headers(client), "X-Tenant-Slug": "tenant-b"},
    )
    assert cross_tenant.status_code == 404


def test_material_rollups_use_cached_candidates(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = signal_service.evaluate_rule_based_risks

    def counted_evaluate(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(signal_service, "evaluate_rule_based_risks", counted_evaluate)
    headers = auth_headers(client)

    first = client.get("/api/v1/signal-engine/material-rollups", headers=headers)
    second = client.get("/api/v1/signal-engine/material-rollups", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert calls == 1


def test_selected_workspace_reuses_cached_base_candidates(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = signal_service.evaluate_rule_based_risks

    def counted_evaluate(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(signal_service, "evaluate_rule_based_risks", counted_evaluate)
    headers = auth_headers(client)

    rollups = client.get("/api/v1/signal-engine/material-rollups", headers=headers)
    assert rollups.status_code == 200
    selected = rollups.json()[0]
    workspace = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=headers,
        params={
            "plant_reference": selected["plant_reference"],
            "material_reference": selected["material_reference"],
        },
    )

    assert workspace.status_code == 200
    assert workspace.json()["empty"] is False
    assert calls == 1


def test_signal_candidate_cache_invalidation_recomputes_for_tenant(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = signal_service.evaluate_rule_based_risks

    def counted_evaluate(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(signal_service, "evaluate_rule_based_risks", counted_evaluate)
    headers = auth_headers(client)

    first = client.get("/api/v1/signal-engine/material-rollups", headers=headers)
    invalidate_signal_candidate_cache(1)
    second = client.get("/api/v1/signal-engine/material-rollups", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls == 2


def test_signal_candidate_cache_is_tenant_scoped() -> None:
    clear_signal_candidate_cache()
    calls = {"tenant_a": 0, "tenant_b": 0}

    def compute_a() -> list[RiskCandidate]:
        calls["tenant_a"] += 1
        return [cache_candidate("P1", "M1")]

    def compute_b() -> list[RiskCandidate]:
        calls["tenant_b"] += 1
        return [cache_candidate("P2", "M2")]

    assert get_cached_signal_candidates(1, compute_a)[0].plant_reference == "P1"
    assert get_cached_signal_candidates(2, compute_b)[0].plant_reference == "P2"
    assert get_cached_signal_candidates(1, compute_a)[0].plant_reference == "P1"
    assert get_cached_signal_candidates(2, compute_b)[0].plant_reference == "P2"

    invalidate_signal_candidate_cache(1)
    assert get_cached_signal_candidates(1, compute_a)[0].plant_reference == "P1"
    assert get_cached_signal_candidates(2, compute_b)[0].plant_reference == "P2"
    assert calls == {"tenant_a": 2, "tenant_b": 1}


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


def test_risk_workspace_default_mode_does_not_require_scenario(
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
    assert body["selected_risk"] is not None
    assert body["selected_risk"]["plant_reference"] == "P1"
    assert body["is_demo_scenario"] is False


def test_risk_workspace_default_mode_works_when_pilot_flag_enabled_for_non_demo_tenant(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "enable_pilot_scenarios", True)

    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["empty"] is False
    assert body["is_demo_scenario"] is False


def test_risk_workspace_scenario_rejected_when_pilot_mode_disabled(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "enable_pilot_scenarios", False)

    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"scenario": "ocean_vessel_delay"},
    )

    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]


def test_risk_workspace_scenario_rejected_for_non_demo_tenant(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "enable_pilot_scenarios", True)

    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"scenario": "ocean_vessel_delay"},
    )

    assert response.status_code == 403
    assert "demo-enabled tenants" in response.json()["detail"]
    with next(app.dependency_overrides[get_db]()) as db:
        assert (
            db.scalar(
                select(Shipment).where(Shipment.shipment_id == "DEMO-MV-EASTERN-LINE-01")
            )
            is None
        )


@pytest.mark.parametrize(
    ("scenario", "expected_labels"),
    [
        ("ocean_vessel_delay", {"Partial protection", "Weak protection"}),
        (
            "inland_movement_failure",
            {"Weak protection", "Not currently protective"},
        ),
        (
            "false_safety",
            {"Partial protection", "Weak protection", "Not currently protective"},
        ),
        ("fresh_verified_inbound", {"Strong protection"}),
        (
            "multi_inbound_mixed_protection",
            {"Strong protection", "Weak protection", "Not currently protective"},
        ),
    ],
)
def test_risk_workspace_demo_scenario_selector_returns_operational_context(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    expected_labels: set[str],
) -> None:
    monkeypatch.setattr(settings, "enable_pilot_scenarios", True)
    enable_demo_tenant()

    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"scenario": scenario},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["empty"] is False
    assert body["is_demo_scenario"] is True
    assert body["scenario_key"] == scenario
    assert body["scenario_label"]
    assert "demo data" in body["demo_data_notice"].lower()
    assert body["selected_risk"] is not None
    assert body["explainability"] is not None
    assert body["explainability"]["reason_chain"]
    assert body["shipment_continuity"]
    labels = {
        item["protective_value_label"]
        for item in body["shipment_continuity"]
        if item["protective_value_label"] is not None
    }
    assert labels & expected_labels
    assert body["selected_risk"]["operational_recommendations"]
    action_text = " ".join(
        " ".join(
            [
                action["action_type"],
                action["operational_reason"],
                *action["supporting_signals"],
                *action["reason_chain"],
            ]
        ).lower()
        for action in body["selected_risk"]["operational_recommendations"]
    )
    assert "reorder" not in action_text
    assert "approve po" not in action_text


def test_risk_workspace_multi_inbound_demo_has_distinct_protection_values(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "enable_pilot_scenarios", True)
    enable_demo_tenant()

    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"scenario": "multi_inbound_mixed_protection"},
    )

    assert response.status_code == 200
    shipments = response.json()["shipment_continuity"]
    labels = {item["shipment_reference"]: item["protective_value_label"] for item in shipments}
    assert labels["DEMO-MV-STRONG-PCI"] == "Strong protection"
    assert labels["DEMO-TRUCK-STALE-PCI"] == "Weak protection"
    assert labels["DEMO-MV-LATE-PCI"] == "Not currently protective"
    protective_quantities = {item["protective_quantity"] for item in shipments}
    assert len(protective_quantities) > 1


def test_risk_workspace_demo_records_are_marked_and_upserted(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "enable_pilot_scenarios", True)
    enable_demo_tenant()

    headers = auth_headers(client)
    for _ in range(2):
        response = client.get(
            "/api/v1/signal-engine/risk-workspace",
            headers=headers,
            params={"scenario": "ocean_vessel_delay"},
        )
        assert response.status_code == 200

    with next(app.dependency_overrides[get_db]()) as db:
        shipments = db.scalars(
            select(Shipment).where(Shipment.shipment_id == "DEMO-MV-EASTERN-LINE-01")
        ).all()
        events = db.scalars(
            select(OperationalEvent).where(
                OperationalEvent.shipment_reference == "DEMO-MV-EASTERN-LINE-01"
            )
        ).all()

    assert len(shipments) == 1
    assert shipments[0].source_of_truth == "pilot_scenario:ocean_vessel_delay"
    assert len(events) == 1
    metadata = events[0].metadata_json or {}
    assert metadata["source"] == "pilot_scenario"
    assert metadata["scenario_key"] == "ocean_vessel_delay"
    assert metadata["demo_data"] is True
    assert metadata["created_for"] == "risk_workspace_pilot_demo"


def test_risk_workspace_unknown_demo_scenario_returns_validation_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "enable_pilot_scenarios", True)
    enable_demo_tenant()

    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"scenario": "not_real"},
    )

    assert response.status_code == 400
    assert "Unsupported pilot scenario" in response.json()["detail"]


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


def test_risk_workspace_returns_insufficient_calibration_when_threshold_missing(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert response.status_code == 200
    body = response.json()
    calibration = body["assessment_calibration"]
    assert calibration["status"] == "INSUFFICIENT_DATA"
    assert Decimal(calibration["score"]) > Decimal("0")
    assert "confidence_score" in body["selected_risk"]
    assert "assessment_calibration" not in body["selected_risk"]


def test_risk_workspace_returns_uncalibrated_when_historical_support_is_limited(
    client: TestClient,
) -> None:
    add_threshold_for_m1()

    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert response.status_code == 200
    calibration = response.json()["assessment_calibration"]
    assert calibration["status"] == "UNCALIBRATED"
    assert "No historical incident replay" in " ".join(calibration["limitations"])
    assert any("historical" in item.lower() for item in calibration["improvement_actions"])


def test_risk_workspace_returns_partially_calibrated_with_detected_history_and_limits(
    client: TestClient,
) -> None:
    add_threshold_for_m1()
    add_line_stop_for_m1()

    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert response.status_code == 200
    calibration = response.json()["assessment_calibration"]
    assert calibration["status"] == "PARTIALLY_CALIBRATED"
    assert Decimal(calibration["score"]) >= Decimal("55")
    assert any("historical" in item.lower() for item in calibration["drivers"])
    assert any("supplier" in item.lower() for item in calibration["limitations"])


def test_risk_workspace_returns_calibrated_when_history_and_data_are_strong(
    client: TestClient,
) -> None:
    add_threshold_for_m1()
    link_supplier_for_m1()
    add_historical_shipment_for_m1()
    refresh_current_visibility_for_m1()
    add_line_stop_for_m1()

    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert response.status_code == 200
    calibration = response.json()["assessment_calibration"]
    assert calibration["status"] == "CALIBRATED"
    assert Decimal(calibration["score"]) >= Decimal("80")
    assert any("prior incident" in item.lower() for item in calibration["drivers"])
    assert any("supplier" in item.lower() for item in calibration["drivers"])


def test_calibration_reduces_when_historical_validation_misses(
    client: TestClient,
) -> None:
    add_threshold_for_m1()
    link_supplier_for_m1()
    add_line_stop_for_m1()
    with next(app.dependency_overrides[get_db]()) as db:
        plant = db.scalar(select(Plant).where(Plant.code == "P1"))
        material = db.scalar(select(Material).where(Material.code == "M1"))
        assert plant is not None
        assert material is not None
        db.add(
            LineStopIncident(
                tenant_id=plant.tenant_id,
                plant_id=plant.id,
                material_id=material.id,
                stopped_at=NOW - timedelta(days=5),
                duration_hours=Decimal("4"),
            )
        )
        db.commit()

    response = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert response.status_code == 200
    calibration = response.json()["assessment_calibration"]
    assert calibration["status"] == "PARTIALLY_CALIBRATED"
    assert any("missed" in item.lower() for item in calibration["limitations"])


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
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def risk_priority_for_test(risk: dict) -> tuple:
    projected = risk["projected_exhaustion_date"]
    projected_sort = (
        datetime.fromisoformat(projected).timestamp()
        if projected is not None
        else float("inf")
    )
    return (
        SEVERITY_ORDER.get(risk["severity"], 99),
        projected_sort,
        risk["risk_type"],
        risk["plant_reference"] or "",
        risk["material_reference"] or "",
        risk["shipment_reference"] or "",
    )


def cache_candidate(plant_reference: str, material_reference: str) -> RiskCandidate:
    return RiskCandidate(
        risk_type="days_of_cover_breach",
        severity="medium",
        plant_reference=plant_reference,
        material_reference=material_reference,
        rule_reasons=["test candidate"],
    )


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


def enable_demo_tenant(slug: str = "tenant-a") -> None:
    with next(app.dependency_overrides[get_db]()) as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
        assert tenant is not None
        tenant.is_demo_tenant = True
        db.commit()


def add_threshold_for_m1() -> None:
    with next(app.dependency_overrides[get_db]()) as db:
        plant = db.scalar(select(Plant).where(Plant.code == "P1"))
        material = db.scalar(select(Material).where(Material.code == "M1"))
        assert plant is not None
        assert material is not None
        db.add(
            PlantMaterialThreshold(
                tenant_id=plant.tenant_id,
                plant_id=plant.id,
                material_id=material.id,
                threshold_days=Decimal("1"),
                warning_days=Decimal("5"),
                minimum_buffer_stock_days=Decimal("2"),
            )
        )
        db.commit()


def add_line_stop_for_m1() -> None:
    with next(app.dependency_overrides[get_db]()) as db:
        plant = db.scalar(select(Plant).where(Plant.code == "P1"))
        material = db.scalar(select(Material).where(Material.code == "M1"))
        assert plant is not None
        assert material is not None
        db.add(
            LineStopIncident(
                tenant_id=plant.tenant_id,
                plant_id=plant.id,
                material_id=material.id,
                stopped_at=NOW + timedelta(days=6),
                duration_hours=Decimal("8"),
            )
        )
        db.commit()


def link_supplier_for_m1() -> None:
    with next(app.dependency_overrides[get_db]()) as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "tenant-a"))
        shipment = db.scalar(select(Shipment).where(Shipment.shipment_id == "SHIP-1"))
        assert tenant is not None
        assert shipment is not None
        supplier = Supplier(
            tenant_id=tenant.id,
            name="Supplier 1",
            code="SUP-1",
            is_active=True,
        )
        db.add(supplier)
        db.flush()
        shipment.supplier_id = supplier.id
        db.commit()


def add_historical_shipment_for_m1() -> None:
    with next(app.dependency_overrides[get_db]()) as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "tenant-a"))
        plant = db.scalar(select(Plant).where(Plant.code == "P1"))
        material = db.scalar(select(Material).where(Material.code == "M1"))
        supplier = db.scalar(select(Supplier).where(Supplier.code == "SUP-1"))
        assert tenant is not None
        assert plant is not None
        assert material is not None
        assert supplier is not None
        db.add(
            Shipment(
                tenant_id=tenant.id,
                shipment_id="HIST-SHIP-1",
                material_id=material.id,
                plant_id=plant.id,
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                quantity_mt=Decimal("50"),
                planned_eta=NOW + timedelta(days=3),
                current_eta=NOW + timedelta(days=3),
                latest_eta=NOW + timedelta(days=2),
                current_milestone="in_transit",
                last_tracking_update_at=NOW + timedelta(days=2),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="historical_validation_fixture",
                latest_update_at=NOW + timedelta(days=2),
            )
        )
        db.commit()


def refresh_current_visibility_for_m1() -> None:
    with next(app.dependency_overrides[get_db]()) as db:
        plant = db.scalar(select(Plant).where(Plant.code == "P1"))
        material = db.scalar(select(Material).where(Material.code == "M1"))
        shipment = db.scalar(select(Shipment).where(Shipment.shipment_id == "SHIP-1"))
        assert plant is not None
        assert material is not None
        assert shipment is not None
        current_time = datetime.now(UTC)
        db.add(
            StockSnapshot(
                tenant_id=plant.tenant_id,
                plant_id=plant.id,
                material_id=material.id,
                on_hand_mt=Decimal("20"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("20"),
                daily_consumption_mt=Decimal("10"),
                snapshot_time=current_time - timedelta(hours=1),
            )
        )
        shipment.planned_eta = current_time + timedelta(days=1)
        shipment.current_eta = current_time + timedelta(days=4)
        shipment.latest_eta = current_time + timedelta(days=1)
        shipment.last_tracking_update_at = current_time - timedelta(hours=2)
        shipment.latest_update_at = current_time - timedelta(hours=2)
        db.commit()


def login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ops@test.local", "password": "Password123!"},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])
