from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Tenant
from app.models.enums import (
    OperationalEventCategory,
    OperationalEventSourceType,
    OperationalEventType,
)
from app.modules.operational_events.schemas import OperationalEventCreate
from app.modules.operational_events.service import create_operational_event
from app.modules.operational_events.timeline import (
    ContinuityTimelineFilters,
    build_continuity_timeline,
    build_timeline_for_risk_candidate,
)
from app.modules.rules.engine import RiskCandidate
from app.schemas.context import RequestContext


def test_timeline_entries_are_built_from_operational_events() -> None:
    with seeded_timeline_session() as (db, tenant_a, _):
        create_event(db, tenant_a.id, event_type=OperationalEventType.INVENTORY_STOCK_UPDATED)
        db.commit()

        entries = build_continuity_timeline(db, context_for(tenant_a))

        assert len(entries) == 1
        assert entries[0].event_type == "inventory_stock_updated"
        assert entries[0].event_id is not None


def test_timeline_entries_are_chronological() -> None:
    with seeded_timeline_session() as (db, tenant_a, _):
        later = datetime(2026, 5, 9, 12, tzinfo=UTC)
        earlier = later - timedelta(hours=2)
        create_event(db, tenant_a.id, occurred_at=later, material_reference="M2")
        create_event(db, tenant_a.id, occurred_at=earlier, material_reference="M1")
        db.commit()

        entries = build_continuity_timeline(db, context_for(tenant_a))

        assert [entry.material_reference for entry in entries] == ["M1", "M2"]


def test_plant_material_filter_works() -> None:
    with seeded_timeline_session() as (db, tenant_a, _):
        create_event(db, tenant_a.id, plant_reference="P1", material_reference="M1")
        create_event(db, tenant_a.id, plant_reference="P1", material_reference="M2")
        create_event(db, tenant_a.id, plant_reference="P2", material_reference="M1")
        db.commit()

        entries = build_continuity_timeline(
            db,
            context_for(tenant_a),
            filters=ContinuityTimelineFilters(plant_reference="P1", material_reference="M1"),
        )

        assert len(entries) == 1
        assert entries[0].plant_reference == "P1"
        assert entries[0].material_reference == "M1"


def test_shipment_filter_works() -> None:
    with seeded_timeline_session() as (db, tenant_a, _):
        create_event(
            db,
            tenant_a.id,
            event_type=OperationalEventType.SHIPMENT_MILESTONE_UPDATED,
            event_category=OperationalEventCategory.SHIPMENT,
            shipment_reference="SHIP-1",
        )
        create_event(
            db,
            tenant_a.id,
            event_type=OperationalEventType.SHIPMENT_MILESTONE_UPDATED,
            event_category=OperationalEventCategory.SHIPMENT,
            shipment_reference="SHIP-2",
        )
        db.commit()

        entries = build_continuity_timeline(
            db,
            context_for(tenant_a),
            filters=ContinuityTimelineFilters(shipment_reference="SHIP-1"),
        )

        assert len(entries) == 1
        assert entries[0].shipment_reference == "SHIP-1"


def test_risk_candidate_context_pulls_relevant_events() -> None:
    with seeded_timeline_session() as (db, tenant_a, _):
        stock_event = create_event(db, tenant_a.id, plant_reference="P1", material_reference="M1")
        shipment_event = create_event(
            db,
            tenant_a.id,
            event_type=OperationalEventType.SHIPMENT_ETA_CHANGED,
            event_category=OperationalEventCategory.SHIPMENT,
            plant_reference="P1",
            material_reference="M1",
            shipment_reference="SHIP-1",
            previous_value={"current_eta": "2026-05-10T12:00:00+00:00"},
            new_value={"current_eta": "2026-05-12T12:00:00+00:00"},
        )
        create_event(db, tenant_a.id, plant_reference="P2", material_reference="M2")
        db.commit()
        db.refresh(stock_event)
        db.refresh(shipment_event)
        candidate = RiskCandidate(
            risk_type="inbound_delay_against_cover",
            severity="high",
            plant_reference="P1",
            material_reference="M1",
            shipment_reference="SHIP-1",
            rule_reasons=["Shipment continuity is degraded"],
            source_event_ids=[shipment_event.id],
        )

        entries = build_timeline_for_risk_candidate(db, context_for(tenant_a), candidate)

        assert [entry.event_id for entry in entries] == [stock_event.id, shipment_event.id]


def test_entries_include_confidence_score_and_freshness_status() -> None:
    with seeded_timeline_session() as (db, tenant_a, _):
        create_event(db, tenant_a.id)
        db.commit()

        entry = build_continuity_timeline(db, context_for(tenant_a))[0]

        assert entry.confidence_score is not None
        assert entry.freshness_status == "fresh"


def test_deterministic_title_and_description_templates_work() -> None:
    with seeded_timeline_session() as (db, tenant_a, _):
        create_event(
            db,
            tenant_a.id,
            event_type=OperationalEventType.SHIPMENT_ETA_CHANGED,
            event_category=OperationalEventCategory.SHIPMENT,
            shipment_reference="SHIP-1",
            previous_value={"current_eta": "2026-05-10T12:00:00+00:00"},
            new_value={"current_eta": "2026-05-12T12:00:00+00:00"},
        )
        db.commit()

        entry = build_continuity_timeline(db, context_for(tenant_a))[0]

        assert entry.title == "Shipment ETA Changed"
        assert (
            entry.description
            == "Shipment SHIP-1 ETA changed from 2026-05-10T12:00:00+00:00 "
            "to 2026-05-12T12:00:00+00:00."
        )


def test_timeline_preserves_tenant_isolation() -> None:
    with seeded_timeline_session() as (db, tenant_a, tenant_b):
        create_event(db, tenant_a.id, plant_reference="P1", material_reference="M1")
        create_event(db, tenant_b.id, plant_reference="P2", material_reference="M2")
        db.commit()

        entries = build_continuity_timeline(db, context_for(tenant_a))

        assert len(entries) == 1
        assert entries[0].plant_reference == "P1"
        assert entries[0].material_reference == "M1"


class seeded_timeline_session:
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
        tenant_a = Tenant(name="Tenant A", slug="tenant-a")
        tenant_b = Tenant(name="Tenant B", slug="tenant-b")
        self.db.add_all([tenant_a, tenant_b])
        self.db.flush()
        return self.db, tenant_a, tenant_b

    def __exit__(self, exc_type, exc_value, traceback):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)


def create_event(
    db: Session,
    tenant_id: int,
    *,
    event_type: OperationalEventType = OperationalEventType.INVENTORY_STOCK_UPDATED,
    event_category: OperationalEventCategory = OperationalEventCategory.INVENTORY,
    source_type: OperationalEventSourceType = OperationalEventSourceType.FILE_INGESTION,
    occurred_at: datetime = datetime(2026, 5, 9, 12, tzinfo=UTC),
    plant_reference: str | None = "P1",
    material_reference: str | None = "M1",
    shipment_reference: str | None = None,
    previous_value: dict | None = None,
    new_value: dict | None = None,
):
    return create_operational_event(
        db,
        OperationalEventCreate(
            tenant_id=tenant_id,
            event_type=event_type,
            event_category=event_category,
            source_type=source_type,
            source_reference=source_type.value,
            occurred_at=occurred_at,
            detected_at=datetime(2026, 5, 9, 12, tzinfo=UTC),
            plant_reference=plant_reference,
            material_reference=material_reference,
            shipment_reference=shipment_reference,
            quantity_value=Decimal("100"),
            quantity_unit="MT",
            previous_value=previous_value,
            new_value=new_value or {"available_to_consume_mt": "100"},
        ),
    )


def context_for(tenant: Tenant) -> RequestContext:
    return RequestContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        role="tenant_admin",
        user_id=1,
    )
