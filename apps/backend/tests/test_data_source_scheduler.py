from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import ExternalDataSource, Tenant
from app.modules.tenants.scheduler import is_source_due, process_due_data_sources_once
from app.modules.tenants.service import classify_data_freshness
from app.modules.tenants.sync_service import compute_change_signals


def test_classify_data_freshness() -> None:
    now = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    assert classify_data_freshness(now - timedelta(minutes=30), 60, now=now) == ("fresh", 30)
    assert classify_data_freshness(now - timedelta(minutes=80), 60, now=now) == ("aging", 80)
    assert classify_data_freshness(now - timedelta(minutes=100), 60, now=now) == ("stale", 100)


def test_change_signal_generation() -> None:
    before = {
        "critical": {(1, 1)},
        "at_risk": {(1, 1), (1, 2)},
        "breached_actions": {(1, 2)},
    }
    after = {
        "critical": {(1, 1), (2, 2)},
        "at_risk": {(1, 1), (2, 2)},
        "breached_actions": {(1, 2), (2, 2)},
    }
    assert compute_change_signals(before, after) == {
        "new_critical_risks_count": 1,
        "resolved_risks_count": 1,
        "newly_breached_actions_count": 1,
    }


def test_scheduler_triggers_due_sync_and_continues_after_failure(monkeypatch) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session() as db:
        tenant = Tenant(name="Tenant A", slug="tenant-a", plan_tier="paid")
        db.add(tenant)
        db.flush()
        db.add_all(
            [
                ExternalDataSource(
                    tenant_id=tenant.id,
                    source_type="google_sheets",
                    source_url="https://docs.google.com/spreadsheets/d/a/edit#gid=0",
                    source_name="First",
                    dataset_type="shipments",
                    sync_frequency_minutes=60,
                    is_active=True,
                    last_synced_at=datetime.now(UTC) - timedelta(minutes=70),
                ),
                ExternalDataSource(
                    tenant_id=tenant.id,
                    source_type="google_sheets",
                    source_url="https://docs.google.com/spreadsheets/d/b/edit#gid=0",
                    source_name="Second",
                    dataset_type="shipments",
                    sync_frequency_minutes=60,
                    is_active=True,
                    last_synced_at=datetime.now(UTC) - timedelta(minutes=90),
                ),
            ]
        )
        db.commit()

    called_ids: list[int] = []

    def fake_sync(db, *, context, current_user_id, source):
        called_ids.append(source.id)
        if source.source_name == "First":
            raise RuntimeError("sync failed")
        source.last_sync_status = "succeeded"
        source.last_synced_at = datetime.now(UTC)
        db.commit()
        return {}

    from app.modules.tenants import scheduler

    monkeypatch.setattr(scheduler, "SessionLocal", testing_session)
    monkeypatch.setattr(scheduler, "sync_loaded_data_source", fake_sync)
    monkeypatch.setattr(scheduler, "resolve_scheduler_user_id", lambda db, tenant_id: None)

    process_due_data_sources_once()

    assert len(called_ids) == 2
    with testing_session() as db:
        second = db.get(ExternalDataSource, 2)
        assert second is not None
        assert second.last_sync_status == "succeeded"

    Base.metadata.drop_all(bind=engine)


def test_is_source_due() -> None:
    source = ExternalDataSource(
        tenant_id=1,
        source_type="google_sheets",
        source_url="https://docs.google.com/spreadsheets/d/a/edit#gid=0",
        source_name="Due Check",
        dataset_type="shipments",
        sync_frequency_minutes=60,
        is_active=True,
        last_synced_at=datetime(2026, 4, 21, 10, 0, tzinfo=UTC),
    )
    assert is_source_due(source, datetime(2026, 4, 21, 11, 0, tzinfo=UTC)) is True
    assert is_source_due(source, datetime(2026, 4, 21, 10, 30, tzinfo=UTC)) is False
