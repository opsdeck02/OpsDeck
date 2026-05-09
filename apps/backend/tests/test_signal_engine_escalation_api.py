from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import ContinuityRiskSnapshot, StockSnapshot, Tenant
from app.modules.risk_snapshots.service import risk_fingerprint
from tests.test_signal_engine_api import auth_headers, seed_signal_engine_data

NOW = datetime(2026, 5, 9, 12, tzinfo=UTC)


@pytest.fixture()
def escalation_client() -> Generator[tuple[TestClient, sessionmaker], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as db:
        seed_signal_engine_data(db)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), testing_session_local
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_controlled_evaluation_records_snapshots_for_current_risk_candidates(
    escalation_client: tuple[TestClient, sessionmaker],
) -> None:
    client, session_local = escalation_client

    response = client.post(
        "/api/v1/signal-engine/evaluate-escalation",
        headers=auth_headers(client),
        params={"snapshot_time": NOW.isoformat()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["snapshots_recorded"] == len(body["risks"])
    assert any(risk["escalation_state"] == "newly_exposed" for risk in body["risks"])
    with session_local() as db:
        snapshots = db.scalars(select(ContinuityRiskSnapshot)).all()
        assert len(snapshots) == body["snapshots_recorded"]
        assert all(snapshot.tenant_id == tenant_a_id(db) for snapshot in snapshots)


def test_second_evaluation_compares_against_prior_snapshot_and_returns_worsening(
    escalation_client: tuple[TestClient, sessionmaker],
) -> None:
    client, session_local = escalation_client
    first = client.post(
        "/api/v1/signal-engine/evaluate-escalation",
        headers=auth_headers(client),
        params={
            "risk_type": "days_of_cover_breach",
            "plant_reference": "P1",
            "material_reference": "M1",
            "snapshot_time": NOW.isoformat(),
        },
    )
    assert first.status_code == 200

    with session_local() as db:
        stock = db.scalar(select(StockSnapshot).where(StockSnapshot.tenant_id == tenant_a_id(db)))
        assert stock is not None
        stock.on_hand_mt = Decimal("10")
        stock.available_to_consume_mt = Decimal("10")
        db.commit()

    second = client.post(
        "/api/v1/signal-engine/evaluate-escalation",
        headers=auth_headers(client),
        params={
            "risk_type": "days_of_cover_breach",
            "plant_reference": "P1",
            "material_reference": "M1",
            "snapshot_time": (NOW + timedelta(hours=1)).isoformat(),
        },
    )

    assert second.status_code == 200
    risks = second.json()["risks"]
    doc_risk = next(risk for risk in risks if risk["risk_type"] == "days_of_cover_breach")
    assert doc_risk["escalation_state"] == "worsening"
    assert Decimal(doc_risk["prior_days_of_cover"]) == Decimal("2")
    assert Decimal(doc_risk["current_days_of_cover"]) == Decimal("1")
    assert Decimal(doc_risk["days_of_cover_delta"]) == Decimal("-1")


def test_risk_api_exposes_recorded_escalation_fields(
    escalation_client: tuple[TestClient, sessionmaker],
) -> None:
    client, _ = escalation_client
    response = client.post(
        "/api/v1/signal-engine/evaluate-escalation",
        headers=auth_headers(client),
        params={"snapshot_time": NOW.isoformat()},
    )
    assert response.status_code == 200

    risks_response = client.get(
        "/api/v1/signal-engine/risks",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert risks_response.status_code == 200
    risk = risks_response.json()[0]
    assert "escalation_state" in risk
    assert "escalation_score" in risk
    assert "prior_days_of_cover" in risk
    assert risk["escalation_state"] == "newly_exposed"


def test_risk_workspace_selected_risk_exposes_escalation_fields(
    escalation_client: tuple[TestClient, sessionmaker],
) -> None:
    client, _ = escalation_client
    response = client.post(
        "/api/v1/signal-engine/evaluate-escalation",
        headers=auth_headers(client),
        params={"snapshot_time": NOW.isoformat()},
    )
    assert response.status_code == 200

    workspace = client.get(
        "/api/v1/signal-engine/risk-workspace",
        headers=auth_headers(client),
        params={"plant_reference": "P1", "material_reference": "M1"},
    )

    assert workspace.status_code == 200
    selected = workspace.json()["selected_risk"]
    assert selected["escalation_state"] == "newly_exposed"
    assert selected["escalation_score"] is not None
    assert selected["escalation_reason"]


def test_same_run_evaluation_is_idempotent_for_snapshot_time(
    escalation_client: tuple[TestClient, sessionmaker],
) -> None:
    client, session_local = escalation_client
    params = {
        "risk_type": "days_of_cover_breach",
        "plant_reference": "P1",
        "material_reference": "M1",
        "snapshot_time": NOW.isoformat(),
    }

    first = client.post(
        "/api/v1/signal-engine/evaluate-escalation",
        headers=auth_headers(client),
        params=params,
    )
    second = client.post(
        "/api/v1/signal-engine/evaluate-escalation",
        headers=auth_headers(client),
        params=params,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    with session_local() as db:
        snapshots = db.scalars(select(ContinuityRiskSnapshot)).all()
        assert len(snapshots) == 1


def test_escalation_evaluation_preserves_tenant_isolation(
    escalation_client: tuple[TestClient, sessionmaker],
) -> None:
    client, session_local = escalation_client
    tenant_b_fingerprint = risk_fingerprint(
        tenant_id=2,
        risk_type="days_of_cover_breach",
        plant_reference="P1",
        material_reference="M1",
        shipment_reference=None,
    )
    with session_local() as db:
        db.add(
            ContinuityRiskSnapshot(
                tenant_id=2,
                risk_fingerprint=tenant_b_fingerprint,
                risk_type="days_of_cover_breach",
                severity="critical",
                plant_reference="P1",
                material_reference="M1",
                snapshot_time=NOW - timedelta(hours=1),
                days_of_cover=Decimal("10"),
            )
        )
        db.commit()

    response = client.post(
        "/api/v1/signal-engine/evaluate-escalation",
        headers=auth_headers(client),
        params={
            "risk_type": "days_of_cover_breach",
            "plant_reference": "P1",
            "material_reference": "M1",
            "snapshot_time": NOW.isoformat(),
        },
    )

    assert response.status_code == 200
    risk = response.json()["risks"][0]
    assert risk["escalation_state"] == "newly_exposed"


def tenant_a_id(db: Session) -> int:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == "tenant-a"))
    assert tenant is not None
    return tenant.id
