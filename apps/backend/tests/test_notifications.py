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
from app.models import (
    ContinuityRiskSnapshot,
    LineStopIncident,
    Material,
    NotificationDeliveryLog,
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
from app.modules.auth.constants import TENANT_ADMIN
from app.modules.auth.security import hash_password
from app.modules.notifications.service import (
    TYPE_CRITICAL_ALERT,
    TYPE_WEEKLY_DIGEST,
    risk_changes_for_digest,
    send_critical_alerts,
    send_due_critical_alerts_once,
    send_due_weekly_digests_once,
)
from app.modules.operational_events.schemas import OperationalEventCreate
from app.modules.operational_events.service import create_operational_event
from app.modules.reports.service import build_executive_continuity_report
from app.modules.signal_engine.candidate_cache import clear_signal_candidate_cache
from app.schemas.context import RequestContext

NOW = datetime(2026, 6, 14, 8, 0, tzinfo=UTC)


class RecordingSender:
    def __init__(self) -> None:
        self.messages = []

    def send(self, message) -> None:
        self.messages.append(message)


def test_notification_settings_persist_and_are_tenant_scoped(
    client: TestClient,
) -> None:
    headers = auth_headers(client)
    payload = {
        "critical_alerts_enabled": True,
        "weekly_digest_enabled": False,
        "recipients_to": ["plant.head@example.com", "ops.manager@example.com"],
        "recipients_cc": ["coo@example.com"],
        "pilot_contacts": ["sponsor@example.com"],
        "digest_day": "monday",
        "digest_time": "08:00",
        "tenant_timezone": "Asia/Kolkata",
        "cooldown_hours": 12,
    }

    response = client.put("/api/v1/notifications/settings", headers=headers, json=payload)
    assert response.status_code == 200
    assert response.json()["weekly_digest_enabled"] is False
    assert response.json()["recipients_to"] == [
        "plant.head@example.com",
        "ops.manager@example.com",
    ]

    cross_tenant = client.get(
        "/api/v1/notifications/settings",
        headers={**headers, "X-Tenant-Slug": "tenant-b"},
    )
    assert cross_tenant.status_code == 404


def test_critical_alert_generation_and_delivery_logging(client: TestClient) -> None:
    configure_recipients(client)
    sender = RecordingSender()
    with next(app.dependency_overrides[get_db]()) as db:
        result = send_critical_alerts(
            db,
            context(),
            sender=sender,
            now=NOW,
        )
        logs = db.scalars(select(NotificationDeliveryLog)).all()

    assert result.status == "SENT"
    assert result.notification_type == TYPE_CRITICAL_ALERT
    assert "[OpsDeck] Critical Continuity Exposure Detected" == result.subject
    assert sender.messages
    assert "Critical Continuity Exposure Detected" in sender.messages[0].body
    assert len(logs) == 2
    assert {log.status for log in logs} == {"SENT"}
    assert all(log.condition_key for log in logs)


def test_duplicate_critical_alerts_are_suppressed_during_cooldown(
    client: TestClient,
) -> None:
    configure_recipients(client)
    sender = RecordingSender()
    with next(app.dependency_overrides[get_db]()) as db:
        first = send_critical_alerts(db, context(), sender=sender, now=NOW)
        second = send_critical_alerts(
            db,
            context(),
            sender=sender,
            now=NOW + timedelta(hours=1),
        )

    assert first.status == "SENT"
    assert second.status == "SKIPPED"
    assert "cooldown" in (second.skipped_reason or "").lower()
    assert len(sender.messages) == 1


def test_due_critical_alert_scan_sends_once_during_cooldown(client: TestClient) -> None:
    configure_recipients(client)
    with next(app.dependency_overrides[get_db]()) as db:
        first_count = send_due_critical_alerts_once(db, now=NOW)
        second_count = send_due_critical_alerts_once(
            db,
            now=NOW + timedelta(minutes=5),
        )
        sent_logs = db.scalars(
            select(NotificationDeliveryLog).where(
                NotificationDeliveryLog.notification_type == TYPE_CRITICAL_ALERT,
                NotificationDeliveryLog.status == "SENT",
            )
        ).all()

    assert first_count == 1
    assert second_count == 0
    assert len(sent_logs) == 2


def test_weekly_digest_generation_reuses_executive_report(client: TestClient) -> None:
    configure_recipients(client)
    response = client.post("/api/v1/notifications/test-digest", headers=auth_headers(client))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SENT"
    assert body["subject"] == "OpsDeck Weekly Continuity Digest"
    with next(app.dependency_overrides[get_db]()) as db:
        log = db.scalar(
            select(NotificationDeliveryLog).where(
                NotificationDeliveryLog.notification_type == "weekly_digest"
            )
        )
        assert log is not None
        assert "OpsDeck Weekly Continuity Digest" in log.metadata_json["markdown"]
        report = build_executive_continuity_report(db, context())
    assert str(report.summary.critical_materials) in log.metadata_json["markdown"]


def test_due_weekly_digest_sends_once_per_tenant_local_day(client: TestClient) -> None:
    configure_recipients(client)
    due_time = datetime(2026, 6, 15, 2, 35, tzinfo=UTC)
    with next(app.dependency_overrides[get_db]()) as db:
        first_count = send_due_weekly_digests_once(db, now=due_time)
        second_count = send_due_weekly_digests_once(
            db,
            now=due_time + timedelta(minutes=5),
        )
        sent_logs = db.scalars(
            select(NotificationDeliveryLog).where(
                NotificationDeliveryLog.notification_type == TYPE_WEEKLY_DIGEST,
                NotificationDeliveryLog.status == "SENT",
            )
        ).all()

    assert first_count == 1
    assert second_count == 0
    assert {log.condition_key for log in sent_logs} == {"weekly:2026-06-15"}


def test_risk_change_tracking_labels_new_escalated_and_resolved(
    client: TestClient,
) -> None:
    with next(app.dependency_overrides[get_db]()) as db:
        plant = db.scalar(select(Plant).where(Plant.code == "JAM"))
        material = db.scalar(select(Material).where(Material.code == "COKING_COAL"))
        assert plant is not None
        assert material is not None
        db.add_all(
            [
                ContinuityRiskSnapshot(
                    tenant_id=plant.tenant_id,
                    risk_fingerprint="old-current",
                    risk_type="days_of_cover_breach",
                    severity="medium",
                    plant_reference=plant.code,
                    material_reference=material.code,
                    snapshot_time=NOW - timedelta(days=10),
                ),
                ContinuityRiskSnapshot(
                    tenant_id=plant.tenant_id,
                    risk_fingerprint="old-resolved",
                    risk_type="days_of_cover_breach",
                    severity="critical",
                    plant_reference="JAM",
                    material_reference="RESOLVED_MAT",
                    snapshot_time=NOW - timedelta(days=10),
                ),
            ]
        )
        db.commit()
        report = build_executive_continuity_report(db, context(), generated_at=NOW)
        changes = risk_changes_for_digest(db, context(), report.critical_materials, sent_at=NOW)

    assert any(item.startswith("ESCALATED") for item in changes["escalated"])
    assert any(item.startswith("RESOLVED") for item in changes["resolved"])


def test_test_critical_alert_endpoint_works(client: TestClient) -> None:
    configure_recipients(client)
    response = client.post(
        "/api/v1/notifications/test-critical-alert",
        headers=auth_headers(client),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "SENT"


def configure_recipients(client: TestClient) -> None:
    response = client.put(
        "/api/v1/notifications/settings",
        headers=auth_headers(client),
        json={
            "critical_alerts_enabled": True,
            "weekly_digest_enabled": True,
            "recipients_to": ["plant.head@example.com"],
            "recipients_cc": ["coo@example.com"],
            "pilot_contacts": [],
            "digest_day": "monday",
            "digest_time": "08:00",
            "tenant_timezone": "Asia/Kolkata",
            "cooldown_hours": 24,
        },
    )
    assert response.status_code == 200


def seed_notification_data(db: Session) -> None:
    tenant_a = Tenant(name="Tenant A Steel", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B Steel", slug="tenant-b")
    role = Role(name=TENANT_ADMIN, description="Tenant admin")
    db.add_all([tenant_a, tenant_b, role])
    db.flush()

    user = User(
        email="admin@test.local",
        full_name="Admin User",
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

    plant = Plant(tenant_id=tenant_a.id, code="JAM", name="Jamshedpur", location="Jharkhand")
    material = Material(
        tenant_id=tenant_a.id,
        code="COKING_COAL",
        name="Imported Coking Coal",
        category="coal",
        uom="MT",
    )
    supplier = Supplier(
        tenant_id=tenant_a.id,
        name="Supplier 1",
        code="SUP-1",
        is_active=True,
    )
    db.add_all([plant, material, supplier])
    db.flush()
    db.add_all(
        [
            StockSnapshot(
                tenant_id=tenant_a.id,
                plant_id=plant.id,
                material_id=material.id,
                on_hand_mt=Decimal("20"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("20"),
                daily_consumption_mt=Decimal("10"),
                snapshot_time=NOW,
            ),
            PlantMaterialThreshold(
                tenant_id=tenant_a.id,
                plant_id=plant.id,
                material_id=material.id,
                threshold_days=Decimal("3"),
                warning_days=Decimal("5"),
                minimum_buffer_stock_days=Decimal("2"),
            ),
            Shipment(
                tenant_id=tenant_a.id,
                shipment_id="SHIP-CRIT-1",
                material_id=material.id,
                plant_id=plant.id,
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                quantity_mt=Decimal("50"),
                planned_eta=NOW + timedelta(days=1),
                current_eta=NOW + timedelta(days=5),
                latest_eta=NOW + timedelta(days=1),
                current_milestone="in_transit",
                last_tracking_update_at=NOW - timedelta(hours=2),
                current_state=ShipmentState.IN_TRANSIT,
                source_of_truth="file_ingestion",
                latest_update_at=NOW - timedelta(hours=2),
            ),
            LineStopIncident(
                tenant_id=tenant_a.id,
                plant_id=plant.id,
                material_id=material.id,
                stopped_at=NOW + timedelta(days=6),
                duration_hours=Decimal("8"),
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
            plant_reference=plant.code,
            material_reference=material.code,
            quantity_value=Decimal("20"),
            quantity_unit="MT",
            new_value={"available_to_consume_mt": "20"},
        ),
    )
    db.commit()


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.local", "password": "Password123!"},
    )
    assert response.status_code == 200
    return {
        "Authorization": f"Bearer {response.json()['access_token']}",
        "X-Tenant-Slug": "tenant-a",
    }


def context() -> RequestContext:
    return RequestContext(
        tenant_id=1,
        tenant_slug="tenant-a",
        role=TENANT_ADMIN,
        user_id=1,
    )


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    clear_signal_candidate_cache()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    with testing_session() as db:
        seed_notification_data(db)

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
        clear_signal_candidate_cache()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
