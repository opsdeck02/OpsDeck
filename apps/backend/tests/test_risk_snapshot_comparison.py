from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import ContinuityRiskSnapshot, Tenant
from app.modules.risk_snapshots.comparison import classify_snapshot_escalation
from app.modules.risk_snapshots.service import risk_fingerprint

NOW = datetime(2026, 5, 9, 12, tzinfo=UTC)


def test_no_previous_snapshot_is_newly_exposed() -> None:
    with snapshot_session() as (db, tenant):
        current = add_snapshot(db, tenant, snapshot_time=NOW)

        comparison = classify_snapshot_escalation(db, current)

        assert comparison.escalation_state == "newly_exposed"
        assert comparison.escalation_score == Decimal("70")
        assert comparison.prior_days_of_cover is None


def test_doc_decrease_by_half_day_is_worsening() -> None:
    with snapshot_session() as (db, tenant):
        add_snapshot(db, tenant, snapshot_time=NOW - timedelta(hours=1), days_of_cover="3.0")
        current = add_snapshot(db, tenant, snapshot_time=NOW, days_of_cover="2.5")

        comparison = classify_snapshot_escalation(db, current)

        assert comparison.escalation_state == "worsening"
        assert comparison.days_of_cover_delta == Decimal("-0.5000")


def test_doc_decrease_by_one_and_half_days_is_rapidly_worsening() -> None:
    with snapshot_session() as (db, tenant):
        add_snapshot(db, tenant, snapshot_time=NOW - timedelta(hours=1), days_of_cover="3.0")
        current = add_snapshot(db, tenant, snapshot_time=NOW, days_of_cover="1.5")

        comparison = classify_snapshot_escalation(db, current)

        assert comparison.escalation_state == "rapidly_worsening"
        assert comparison.days_of_cover_delta == Decimal("-1.5000")


def test_shipment_delay_increase_by_six_hours_is_worsening() -> None:
    with snapshot_session() as (db, tenant):
        add_snapshot(
            db,
            tenant,
            snapshot_time=NOW - timedelta(hours=1),
            shipment_delay_hours="12",
        )
        current = add_snapshot(db, tenant, snapshot_time=NOW, shipment_delay_hours="18")

        comparison = classify_snapshot_escalation(db, current)

        assert comparison.escalation_state == "worsening"
        assert comparison.shipment_delay_delta_hours == Decimal("6.00")


def test_shipment_delay_increase_by_twenty_four_hours_is_rapidly_worsening() -> None:
    with snapshot_session() as (db, tenant):
        add_snapshot(
            db,
            tenant,
            snapshot_time=NOW - timedelta(hours=1),
            shipment_delay_hours="12",
        )
        current = add_snapshot(db, tenant, snapshot_time=NOW, shipment_delay_hours="36")

        comparison = classify_snapshot_escalation(db, current)

        assert comparison.escalation_state == "rapidly_worsening"
        assert comparison.shipment_delay_delta_hours == Decimal("24.00")


def test_doc_increase_by_half_day_is_recovering() -> None:
    with snapshot_session() as (db, tenant):
        add_snapshot(db, tenant, snapshot_time=NOW - timedelta(hours=1), days_of_cover="2.0")
        current = add_snapshot(db, tenant, snapshot_time=NOW, days_of_cover="2.5")

        comparison = classify_snapshot_escalation(db, current)

        assert comparison.escalation_state == "recovering"
        assert comparison.escalation_score == Decimal("35")


def test_stable_values_are_contained() -> None:
    with snapshot_session() as (db, tenant):
        add_snapshot(
            db,
            tenant,
            snapshot_time=NOW - timedelta(hours=1),
            days_of_cover="3.0",
            shipment_delay_hours="12",
            exposure_level="watch",
        )
        current = add_snapshot(
            db,
            tenant,
            snapshot_time=NOW,
            days_of_cover="3.0",
            shipment_delay_hours="12",
            exposure_level="watch",
        )

        comparison = classify_snapshot_escalation(db, current)

        assert comparison.escalation_state == "contained"


def test_high_stale_snapshot_is_blind_spot_unless_rapidly_worsening() -> None:
    with snapshot_session() as (db, tenant):
        add_snapshot(
            db,
            tenant,
            snapshot_time=NOW - timedelta(hours=1),
            days_of_cover="3.0",
            freshness_status="fresh",
        )
        current = add_snapshot(
            db,
            tenant,
            snapshot_time=NOW,
            days_of_cover="3.0",
            freshness_status="stale",
            severity="high",
        )

        comparison = classify_snapshot_escalation(db, current)

        assert comparison.escalation_state == "blind_spot_risk"

    with snapshot_session() as (db, tenant):
        add_snapshot(
            db,
            tenant,
            snapshot_time=NOW - timedelta(hours=1),
            days_of_cover="3.0",
            freshness_status="fresh",
        )
        current = add_snapshot(
            db,
            tenant,
            snapshot_time=NOW,
            days_of_cover="1.0",
            freshness_status="stale",
            severity="critical",
        )

        comparison = classify_snapshot_escalation(db, current)

        assert comparison.escalation_state == "rapidly_worsening"


def test_severity_worsening_to_critical_is_rapidly_worsening() -> None:
    with snapshot_session() as (db, tenant):
        add_snapshot(db, tenant, snapshot_time=NOW - timedelta(hours=1), severity="high")
        current = add_snapshot(db, tenant, snapshot_time=NOW, severity="critical")

        comparison = classify_snapshot_escalation(db, current)

        assert comparison.escalation_state == "rapidly_worsening"
        assert comparison.prior_severity == "high"
        assert comparison.current_severity == "critical"


def test_escalation_score_is_deterministic_and_clamped() -> None:
    with snapshot_session() as (db, tenant):
        add_snapshot(
            db,
            tenant,
            snapshot_time=NOW - timedelta(hours=1),
            days_of_cover="4.0",
            severity="high",
            exposure_level="near_term",
        )
        current = add_snapshot(
            db,
            tenant,
            snapshot_time=NOW,
            days_of_cover="1.0",
            severity="critical",
            exposure_level="immediate",
            freshness_status="critical",
        )

        first = classify_snapshot_escalation(db, current)
        second = classify_snapshot_escalation(db, current)

        assert first.escalation_score == Decimal("100")
        assert second.escalation_score == first.escalation_score


def test_current_snapshot_can_be_updated_with_escalation_fields() -> None:
    with snapshot_session() as (db, tenant):
        add_snapshot(db, tenant, snapshot_time=NOW - timedelta(hours=1), days_of_cover="3.0")
        current = add_snapshot(db, tenant, snapshot_time=NOW, days_of_cover="2.0")

        comparison = classify_snapshot_escalation(db, current, update_snapshot=True)
        db.commit()

        assert current.escalation_state == comparison.escalation_state
        assert current.escalation_score == comparison.escalation_score
        assert current.escalation_reason == comparison.escalation_reason


def test_escalation_comparison_preserves_tenant_isolation() -> None:
    with snapshot_session() as (db, tenant_a):
        tenant_b = Tenant(name="Tenant B", slug="tenant-b")
        db.add(tenant_b)
        db.flush()
        current = add_snapshot(db, tenant_a, snapshot_time=NOW)
        add_snapshot(
            db,
            tenant_b,
            snapshot_time=NOW - timedelta(hours=1),
            risk_fingerprint_override=current.risk_fingerprint,
            days_of_cover="1.0",
        )

        comparison = classify_snapshot_escalation(db, current)

        assert comparison.escalation_state == "newly_exposed"
        assert comparison.prior_days_of_cover is None


class snapshot_session:
    def __enter__(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.session_local = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
        )
        Base.metadata.create_all(bind=self.engine)
        self.db = self.session_local()
        tenant = Tenant(name="Tenant A", slug="tenant-a")
        self.db.add(tenant)
        self.db.flush()
        return self.db, tenant

    def __exit__(self, exc_type, exc, tb):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()


def add_snapshot(
    db,
    tenant: Tenant,
    *,
    snapshot_time: datetime,
    risk_fingerprint_override: str | None = None,
    risk_type: str = "days_of_cover_breach",
    severity: str = "high",
    plant_reference: str = "P1",
    material_reference: str = "M1",
    shipment_reference: str | None = "SHIP-1",
    days_of_cover: str | None = "3.0",
    exposure_level: str | None = "near_term",
    shipment_delay_hours: str | None = "12",
    freshness_status: str | None = "fresh",
) -> ContinuityRiskSnapshot:
    fingerprint = risk_fingerprint_override or risk_fingerprint(
        tenant_id=tenant.id,
        risk_type=risk_type,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
    )
    snapshot = ContinuityRiskSnapshot(
        tenant_id=tenant.id,
        risk_fingerprint=fingerprint,
        risk_type=risk_type,
        severity=severity,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
        snapshot_time=snapshot_time,
        days_of_cover=Decimal(days_of_cover) if days_of_cover is not None else None,
        exposure_level=exposure_level,
        shipment_delay_hours=(
            Decimal(shipment_delay_hours) if shipment_delay_hours is not None else None
        ),
        freshness_status=freshness_status,
    )
    db.add(snapshot)
    db.flush()
    return snapshot
