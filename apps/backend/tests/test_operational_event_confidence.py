from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import OperationalEvent, Tenant
from app.models.enums import (
    OperationalEventCategory,
    OperationalEventFreshnessStatus,
    OperationalEventSourceType,
    OperationalEventType,
)
from app.modules.operational_events.confidence import calculate_confidence
from app.modules.operational_events.freshness import classify_event_freshness
from app.modules.operational_events.schemas import OperationalEventCreate
from app.modules.operational_events.service import create_operational_event


def test_missing_important_references_lowers_confidence() -> None:
    detected_at = datetime(2026, 5, 9, 12, tzinfo=UTC)
    complete = inventory_payload(detected_at)
    incomplete = inventory_payload(
        detected_at,
        plant_reference=None,
        material_reference=None,
        quantity_value=None,
    )

    complete_confidence = calculate_confidence(complete, detected_at)
    incomplete_confidence = calculate_confidence(incomplete, detected_at)

    assert incomplete_confidence.score < complete_confidence.score
    assert (
        incomplete_confidence.factors["completeness"]
        < complete_confidence.factors["completeness"]
    )
    assert any("Missing category references" in reason for reason in incomplete_confidence.reasons)


def test_older_occurred_at_lowers_confidence() -> None:
    detected_at = datetime(2026, 5, 9, 12, tzinfo=UTC)
    fresh = inventory_payload(detected_at, occurred_at=detected_at - timedelta(hours=2))
    stale = inventory_payload(detected_at, occurred_at=detected_at - timedelta(days=45))

    fresh_confidence = calculate_confidence(fresh, detected_at)
    stale_confidence = calculate_confidence(stale, detected_at)

    assert stale_confidence.score < fresh_confidence.score
    assert stale_confidence.factors["freshness"] < fresh_confidence.factors["freshness"]


def test_unknown_source_type_gets_lower_confidence() -> None:
    detected_at = datetime(2026, 5, 9, 12, tzinfo=UTC)
    trusted = inventory_payload(detected_at, source_type=OperationalEventSourceType.FILE_INGESTION)
    unknown = inventory_payload(detected_at, source_type=OperationalEventSourceType.UNKNOWN)

    trusted_confidence = calculate_confidence(trusted, detected_at)
    unknown_confidence = calculate_confidence(unknown, detected_at)

    assert unknown_confidence.score < trusted_confidence.score
    assert unknown_confidence.factors["source_reliability"] == 50
    assert unknown_confidence.factors["validation"] < trusted_confidence.factors["validation"]


def test_operational_event_confidence_preserves_tenant_isolation() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            tenant_a = Tenant(name="Tenant A", slug="tenant-a")
            tenant_b = Tenant(name="Tenant B", slug="tenant-b")
            db.add_all([tenant_a, tenant_b])
            db.flush()
            detected_at = datetime(2026, 5, 9, 12, tzinfo=UTC)
            create_operational_event(db, inventory_payload(detected_at, tenant_id=tenant_a.id))
            create_operational_event(db, inventory_payload(detected_at, tenant_id=tenant_b.id))
            db.commit()

            assert (
                db.scalar(
                    select(func.count(OperationalEvent.id)).where(
                        OperationalEvent.tenant_id == tenant_a.id
                    )
                )
                == 1
            )
            assert (
                db.scalar(
                    select(func.count(OperationalEvent.id)).where(
                        OperationalEvent.tenant_id == tenant_b.id
                    )
                )
                == 1
            )
            event = db.scalar(
                select(OperationalEvent).where(OperationalEvent.tenant_id == tenant_a.id)
            )
            assert event is not None
            assert event.freshness_status == OperationalEventFreshnessStatus.FRESH
            assert event.metadata_json is not None
            assert "confidence" in event.metadata_json
            assert "freshness" in event.metadata_json
    finally:
        Base.metadata.drop_all(bind=engine)


def test_old_inventory_event_gets_critical_freshness() -> None:
    detected_at = datetime(2026, 5, 9, 12, tzinfo=UTC)
    event = create_persisted_event(
        inventory_payload(detected_at, occurred_at=detected_at - timedelta(days=5))
    )

    assert event.freshness_status == OperationalEventFreshnessStatus.CRITICAL
    assert event.metadata_json is not None
    assert event.metadata_json["freshness"]["status"] == "critical"
    assert event.metadata_json["freshness"]["threshold_profile"] == "file_upload"


def test_ais_shipment_event_uses_stricter_freshness_threshold() -> None:
    detected_at = datetime(2026, 5, 9, 12, tzinfo=UTC)
    result = classify_event_freshness(
        occurred_at=detected_at - timedelta(hours=2),
        detected_at=detected_at,
        source_type=OperationalEventSourceType.AIS,
    )

    assert result.status == OperationalEventFreshnessStatus.DELAYED
    assert result.threshold_profile == "logistics_feed"


def test_missing_occurred_at_gets_unknown_freshness_with_reason() -> None:
    detected_at = datetime(2026, 5, 9, 12, tzinfo=UTC)
    event = create_persisted_event(
        inventory_payload(detected_at, occurred_at=None, preserve_missing_occurred_at=True)
    )

    assert event.freshness_status == OperationalEventFreshnessStatus.UNKNOWN
    assert event.occurred_at.replace(tzinfo=UTC) == detected_at
    assert event.metadata_json is not None
    assert event.metadata_json["freshness"]["status"] == "unknown"
    assert "detected_at was used" in event.metadata_json["freshness"]["reasons"][0]


def test_future_occurred_at_gets_unknown_freshness_with_reason() -> None:
    detected_at = datetime(2026, 5, 9, 12, tzinfo=UTC)
    event = create_persisted_event(
        inventory_payload(detected_at, occurred_at=detected_at + timedelta(hours=1))
    )

    assert event.freshness_status == OperationalEventFreshnessStatus.UNKNOWN
    assert event.metadata_json is not None
    assert event.metadata_json["freshness"]["age_minutes"] is None
    assert "after detected timestamp" in event.metadata_json["freshness"]["reasons"][0]
    assert "confidence" in event.metadata_json


def create_persisted_event(payload: OperationalEventCreate) -> OperationalEvent:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        tenant = Tenant(name="Tenant A", slug="tenant-a")
        db.add(tenant)
        db.flush()
        event = create_operational_event(
            db,
            payload.model_copy(update={"tenant_id": tenant.id}),
        )
        db.commit()
        db.refresh(event)
        db.expunge(event)
    Base.metadata.drop_all(bind=engine)
    return event


def inventory_payload(
    detected_at: datetime,
    *,
    tenant_id: int = 1,
    occurred_at: datetime | None = None,
    source_type: OperationalEventSourceType = OperationalEventSourceType.FILE_INGESTION,
    plant_reference: str | None = "JAM",
    material_reference: str | None = "COKING_COAL",
    quantity_value: Decimal | None = Decimal("9000"),
    preserve_missing_occurred_at: bool = False,
) -> OperationalEventCreate:
    payload_occurred_at = None if preserve_missing_occurred_at else occurred_at or detected_at
    return OperationalEventCreate(
        tenant_id=tenant_id,
        event_type=OperationalEventType.INVENTORY_STOCK_UPDATED,
        event_category=OperationalEventCategory.INVENTORY,
        source_type=source_type,
        source_reference=source_type.value,
        occurred_at=payload_occurred_at,
        detected_at=detected_at,
        plant_reference=plant_reference,
        material_reference=material_reference,
        quantity_value=quantity_value,
        quantity_unit="MT" if quantity_value is not None else None,
        new_value={"available_to_consume_mt": str(quantity_value)}
        if quantity_value is not None
        else None,
    )
