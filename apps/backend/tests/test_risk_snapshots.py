from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import ContinuityRiskSnapshot, Tenant
from app.modules.exposure.mapping import (
    ExposureTrustSummary,
    OperationalExposureMapping,
)
from app.modules.risk_snapshots.service import (
    create_snapshot_from_risk_candidate,
    risk_fingerprint,
)
from app.modules.rules.engine import RiskCandidate
from app.modules.shipments.continuity import calculate_shipment_continuity
from app.modules.stock.continuity import calculate_inventory_continuity
from app.schemas.context import RequestContext

NOW = datetime(2026, 5, 9, 12, tzinfo=UTC)


def test_snapshot_can_be_created_from_risk_candidate() -> None:
    with snapshot_session() as (db, tenant):
        snapshot = create_snapshot_from_risk_candidate(
            db,
            context_for(tenant),
            candidate(),
            snapshot_time=NOW,
        )
        db.commit()

        assert snapshot.id is not None
        assert snapshot.tenant_id == tenant.id
        assert snapshot.risk_type == "days_of_cover_breach"
        assert snapshot.severity == "critical"


def test_snapshot_includes_plant_material_shipment_context() -> None:
    with snapshot_session() as (db, tenant):
        snapshot = create_snapshot_from_risk_candidate(
            db,
            context_for(tenant),
            candidate(shipment_reference="SHIP-1"),
            snapshot_time=NOW,
        )
        db.commit()

        assert snapshot.plant_reference == "P1"
        assert snapshot.material_reference == "M1"
        assert snapshot.shipment_reference == "SHIP-1"


def test_risk_fingerprint_is_deterministic() -> None:
    first = risk_fingerprint(
        tenant_id=1,
        risk_type="days_of_cover_breach",
        plant_reference="P1",
        material_reference="M1",
        shipment_reference="SHIP-1",
    )
    second = risk_fingerprint(
        tenant_id=1,
        risk_type="days_of_cover_breach",
        plant_reference="p1",
        material_reference="m1",
        shipment_reference="ship-1",
    )

    assert first == second


def test_same_risk_context_generates_same_fingerprint() -> None:
    with snapshot_session() as (_, tenant):
        left = candidate(shipment_reference="SHIP-1")
        right = candidate(shipment_reference="SHIP-1")

        assert risk_fingerprint(
            tenant_id=tenant.id,
            risk_type=left.risk_type,
            plant_reference=left.plant_reference,
            material_reference=left.material_reference,
            shipment_reference=left.shipment_reference,
        ) == risk_fingerprint(
            tenant_id=tenant.id,
            risk_type=right.risk_type,
            plant_reference=right.plant_reference,
            material_reference=right.material_reference,
            shipment_reference=right.shipment_reference,
        )


def test_different_material_plant_or_shipment_generates_different_fingerprint() -> None:
    base = risk_fingerprint(
        tenant_id=1,
        risk_type="days_of_cover_breach",
        plant_reference="P1",
        material_reference="M1",
        shipment_reference="SHIP-1",
    )

    assert base != risk_fingerprint(
        tenant_id=1,
        risk_type="days_of_cover_breach",
        plant_reference="P2",
        material_reference="M1",
        shipment_reference="SHIP-1",
    )
    assert base != risk_fingerprint(
        tenant_id=1,
        risk_type="days_of_cover_breach",
        plant_reference="P1",
        material_reference="M2",
        shipment_reference="SHIP-1",
    )
    assert base != risk_fingerprint(
        tenant_id=1,
        risk_type="days_of_cover_breach",
        plant_reference="P1",
        material_reference="M1",
        shipment_reference="SHIP-2",
    )


def test_snapshot_stores_continuity_exposure_freshness_and_confidence() -> None:
    with snapshot_session() as (db, tenant):
        inventory = calculate_inventory_continuity(
            plant_reference="P1",
            material_reference="M1",
            on_hand_quantity=Decimal("30"),
            blocked_quantity=Decimal("5"),
            daily_consumption_rate=Decimal("10"),
            inbound_committed_quantity=Decimal("20"),
            inbound_uncertain_quantity=Decimal("10"),
            unit="MT",
            now=NOW,
        )
        shipment = calculate_shipment_continuity(
            shipment_reference="SHIP-1",
            eta=NOW + timedelta(days=4),
            previous_eta=NOW + timedelta(days=2),
            tracking_updated_at=NOW - timedelta(hours=10),
            linked_material_reference="M1",
            linked_plant_reference="P1",
            now=NOW,
        )
        snapshot = create_snapshot_from_risk_candidate(
            db,
            context_for(tenant),
            candidate(
                shipment_reference="SHIP-1",
                confidence_score=Decimal("42"),
                freshness_status="stale",
            ),
            snapshot_time=NOW,
            exposure=exposure(),
            inventory_continuity=inventory,
            shipment_continuity=shipment,
            metadata={
                "exposure_value": "125000.50",
                "tracking_freshness_minutes": "600",
            },
        )
        db.commit()

        assert snapshot.days_of_cover == Decimal("2.0000")
        assert snapshot.exposure_level == "immediate"
        assert snapshot.exposure_basis == "projected_stockout"
        assert snapshot.exposure_value == Decimal("125000.50")
        assert snapshot.freshness_status == "stale"
        assert snapshot.confidence_score == Decimal("42.00")
        assert snapshot.usable_stock == Decimal("25.000")
        assert snapshot.blocked_stock == Decimal("5.000")
        assert snapshot.incoming_quantity == Decimal("30.000")
        assert snapshot.shipment_delay_hours == Decimal("48.00")
        assert snapshot.tracking_freshness_minutes == Decimal("600.00")


def test_snapshot_creation_is_idempotent_for_same_run_context() -> None:
    with snapshot_session() as (db, tenant):
        first = create_snapshot_from_risk_candidate(
            db,
            context_for(tenant),
            candidate(),
            snapshot_time=NOW,
        )
        second = create_snapshot_from_risk_candidate(
            db,
            context_for(tenant),
            candidate(confidence_score=Decimal("55")),
            snapshot_time=NOW,
        )
        db.commit()

        snapshots = db.scalars(select(ContinuityRiskSnapshot)).all()
        assert len(snapshots) == 1
        assert first.id == second.id
        assert snapshots[0].confidence_score == Decimal("55.00")


def test_snapshot_tenant_isolation_is_preserved() -> None:
    with snapshot_session() as (db, tenant_a):
        tenant_b = Tenant(name="Tenant B", slug="tenant-b")
        db.add(tenant_b)
        db.flush()

        snapshot_a = create_snapshot_from_risk_candidate(
            db,
            context_for(tenant_a),
            candidate(),
            snapshot_time=NOW,
        )
        snapshot_b = create_snapshot_from_risk_candidate(
            db,
            context_for(tenant_b),
            candidate(),
            snapshot_time=NOW,
        )
        db.commit()

        tenant_a_snapshots = db.scalars(
            select(ContinuityRiskSnapshot).where(
                ContinuityRiskSnapshot.tenant_id == tenant_a.id
            )
        ).all()

        assert len(tenant_a_snapshots) == 1
        assert tenant_a_snapshots[0].id == snapshot_a.id
        assert tenant_a_snapshots[0].id != snapshot_b.id
        assert snapshot_a.risk_fingerprint != snapshot_b.risk_fingerprint


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


def candidate(
    *,
    shipment_reference: str | None = None,
    confidence_score: Decimal | None = None,
    freshness_status: str | None = None,
) -> RiskCandidate:
    return RiskCandidate(
        risk_type="days_of_cover_breach",
        severity="critical",
        plant_reference="P1",
        material_reference="M1",
        shipment_reference=shipment_reference,
        days_of_cover=Decimal("2"),
        projected_exhaustion_date=NOW + timedelta(days=2),
        confidence_score=confidence_score,
        freshness_status=freshness_status,
        rule_reasons=["Days of cover is 2, mapped to critical by threshold"],
        source_event_ids=[1, 2],
    )


def exposure() -> OperationalExposureMapping:
    return OperationalExposureMapping(
        plant_reference="P1",
        material_reference="M1",
        shipment_reference="SHIP-1",
        estimated_exposure_date=NOW + timedelta(days=2),
        days_until_exposure=Decimal("2"),
        exposure_level="immediate",
        exposure_basis="projected_stockout",
        operational_reason="Material M1 at plant P1 is projected to exhaust.",
        trust_summary=ExposureTrustSummary(),
        related_risk_types=["days_of_cover_breach"],
        timeline_event_count=1,
    )


def context_for(tenant: Tenant) -> RequestContext:
    return RequestContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        role="tenant_admin",
        user_id=1,
    )
