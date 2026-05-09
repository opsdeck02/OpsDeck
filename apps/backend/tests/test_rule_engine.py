from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Material, OperationalEvent, Plant, Shipment, StockSnapshot, Tenant
from app.models.enums import (
    OperationalEventCategory,
    OperationalEventFreshnessStatus,
    OperationalEventSourceType,
    OperationalEventType,
    ShipmentState,
)
from app.modules.operational_events.service import create_operational_event
from app.modules.rules.engine import (
    evaluate_event_trust_rules,
    evaluate_inbound_delay_against_cover,
    evaluate_inventory_rules,
    evaluate_rule_based_risks,
    evaluate_shipment_rules,
)
from app.modules.shipments.continuity import calculate_shipment_continuity
from app.modules.stock.continuity import calculate_inventory_continuity
from app.schemas.context import RequestContext


def test_doc_less_than_or_equal_two_creates_critical_risk_candidate() -> None:
    candidates = evaluate_inventory_rules(inventory(days_of_cover=Decimal("2")))

    candidate = only_type(candidates, "days_of_cover_breach")
    assert candidate.severity == "critical"
    assert candidate.rule_reasons


def test_doc_less_than_or_equal_five_creates_high_risk_candidate() -> None:
    candidate = only_type(
        evaluate_inventory_rules(inventory(days_of_cover=Decimal("5"))),
        "days_of_cover_breach",
    )

    assert candidate.severity == "high"


def test_doc_less_than_or_equal_ten_creates_medium_risk_candidate() -> None:
    candidate = only_type(
        evaluate_inventory_rules(inventory(days_of_cover=Decimal("10"))),
        "days_of_cover_breach",
    )

    assert candidate.severity == "medium"


def test_degraded_shipment_creates_shipment_degraded_risk() -> None:
    candidate = only_type(evaluate_shipment_rules(degraded_shipment()), "shipment_degraded")

    assert candidate.severity == "high"
    assert candidate.shipment_reference == "SHIP-1"


def test_degraded_shipment_plus_low_inventory_cover_creates_inbound_delay_risk() -> None:
    candidates = evaluate_inbound_delay_against_cover(
        degraded_shipment(eta_slip_days=Decimal("3")),
        inventory(days_of_cover=Decimal("2")),
    )

    candidate = only_type(candidates, "inbound_delay_against_cover")
    assert candidate.severity == "critical"
    assert candidate.days_of_cover == Decimal("2.00")


def test_stale_or_critical_freshness_creates_stale_signal_risk() -> None:
    event = operational_event(freshness_status=OperationalEventFreshnessStatus.STALE)

    candidate = only_type(evaluate_event_trust_rules(event), "stale_signal_risk")
    assert candidate.severity == "medium"
    assert candidate.source_event_ids == [event.id]


def test_low_confidence_creates_low_confidence_signal_risk() -> None:
    event = operational_event(confidence_score=Decimal("25"))

    candidate = only_type(evaluate_event_trust_rules(event), "low_confidence_signal_risk")
    assert candidate.severity == "high"
    assert candidate.confidence_score == Decimal("25")


def test_missing_context_creates_missing_operational_context_risk() -> None:
    event = operational_event(plant_reference=None, material_reference=None)

    candidate = only_type(evaluate_event_trust_rules(event), "missing_operational_context")
    assert candidate.severity == "low"
    assert candidate.rule_reasons


def test_rule_engine_preserves_tenant_isolation() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            tenant_a, tenant_b = seed_rule_engine_data(db)
            candidates_a = evaluate_rule_based_risks(
                db,
                context_for(tenant_a),
                now=datetime(2026, 5, 9, 12, tzinfo=UTC),
            )
            candidates_b = evaluate_rule_based_risks(
                db,
                context_for(tenant_b),
                now=datetime(2026, 5, 9, 12, tzinfo=UTC),
            )

            assert any(candidate.plant_reference == "P1" for candidate in candidates_a)
            assert not any(candidate.plant_reference == "P2" for candidate in candidates_a)
            assert any(candidate.plant_reference == "P2" for candidate in candidates_b)
            assert not any(candidate.plant_reference == "P1" for candidate in candidates_b)
    finally:
        Base.metadata.drop_all(bind=engine)


def test_every_risk_candidate_includes_explainability() -> None:
    with seeded_rule_engine_session() as (db, tenant_a, _):
        candidates = evaluate_rule_based_risks(
            db,
            context_for(tenant_a),
            now=datetime(2026, 5, 9, 12, tzinfo=UTC),
        )

        assert candidates
        assert all(candidate.explainability is not None for candidate in candidates)


def test_doc_breach_explainability_has_required_sections() -> None:
    candidate = only_type(
        evaluate_inventory_rules(inventory(days_of_cover=Decimal("2"))),
        "days_of_cover_breach",
    )

    assert candidate.explainability is not None
    assert "Material M1 at plant P1 has 2.00 days of cover" in candidate.explainability.summary
    assert candidate.explainability.primary_driver == "inventory_continuity"
    assert candidate.explainability.operational_context.days_of_cover == Decimal("2.00")
    assert candidate.explainability.reason_chain == candidate.rule_reasons


def test_inbound_delay_explainability_includes_inventory_and_shipment_context() -> None:
    candidate = only_type(
        evaluate_inbound_delay_against_cover(
            degraded_shipment(eta_slip_days=Decimal("3")),
            inventory(days_of_cover=Decimal("2")),
        ),
        "inbound_delay_against_cover",
    )

    assert candidate.explainability is not None
    context = candidate.explainability.operational_context
    assert context.plant_reference == "P1"
    assert context.material_reference == "M1"
    assert context.shipment_reference == "SHIP-1"
    assert context.days_of_cover == Decimal("2.00")
    assert context.shipment_continuity_status == "degraded"


def test_stale_freshness_creates_trust_warning() -> None:
    event = operational_event(freshness_status=OperationalEventFreshnessStatus.STALE)
    candidate = only_type(evaluate_event_trust_rules(event), "stale_signal_risk")

    assert candidate.explainability is not None
    assert candidate.explainability.trust_context.worst_freshness_status == "stale"
    assert "Operational signal freshness is stale" in (
        candidate.explainability.trust_context.trust_warnings
    )


def test_low_confidence_creates_trust_warning() -> None:
    event = operational_event(confidence_score=Decimal("25"))
    candidate = only_type(evaluate_event_trust_rules(event), "low_confidence_signal_risk")

    assert candidate.explainability is not None
    assert candidate.explainability.trust_context.lowest_confidence_score == Decimal("25")
    assert "Operational signal confidence is low at 25" in (
        candidate.explainability.trust_context.trust_warnings
    )


def test_contributing_signals_include_confidence_and_freshness() -> None:
    with seeded_rule_engine_session() as (db, tenant_a, _):
        candidates = evaluate_rule_based_risks(
            db,
            context_for(tenant_a),
            now=datetime(2026, 5, 9, 12, tzinfo=UTC),
        )
        candidate = only_type(candidates, "stale_signal_risk")

        assert candidate.explainability is not None
        signal = candidate.explainability.contributing_signals[0]
        assert signal.event_id is not None
        assert signal.confidence_score is not None
        assert signal.freshness_status == "critical"


def test_explainability_payload_is_deterministic() -> None:
    with seeded_rule_engine_session() as (db, tenant_a, _):
        first = [
            candidate.model_dump(mode="json")
            for candidate in evaluate_rule_based_risks(
                db,
                context_for(tenant_a),
                now=datetime(2026, 5, 9, 12, tzinfo=UTC),
            )
        ]
        second = [
            candidate.model_dump(mode="json")
            for candidate in evaluate_rule_based_risks(
                db,
                context_for(tenant_a),
                now=datetime(2026, 5, 9, 12, tzinfo=UTC),
            )
        ]

        assert first == second


def inventory(days_of_cover: Decimal):
    daily_consumption = Decimal("10")
    on_hand = days_of_cover * daily_consumption
    return calculate_inventory_continuity(
        plant_reference="P1",
        material_reference="M1",
        on_hand_quantity=on_hand,
        daily_consumption_rate=daily_consumption,
        unit="MT",
        now=datetime(2026, 5, 9, 12, tzinfo=UTC),
    )


def degraded_shipment(eta_slip_days: Decimal = Decimal("2")):
    now = datetime(2026, 5, 9, 12, tzinfo=UTC)
    previous_eta = now + timedelta(days=1)
    return calculate_shipment_continuity(
        shipment_reference="SHIP-1",
        eta=previous_eta + timedelta(days=float(eta_slip_days)),
        previous_eta=previous_eta,
        current_milestone="in_transit",
        tracking_updated_at=now - timedelta(hours=8),
        linked_purchase_order_reference="PO-1",
        linked_material_reference="M1",
        linked_plant_reference="P1",
        current_state=ShipmentState.IN_TRANSIT,
        now=now,
    )


def operational_event(
    *,
    confidence_score: Decimal = Decimal("80"),
    freshness_status: OperationalEventFreshnessStatus = OperationalEventFreshnessStatus.FRESH,
    plant_reference: str | None = "P1",
    material_reference: str | None = "M1",
) -> OperationalEvent:
    return OperationalEvent(
        id=123,
        tenant_id=1,
        event_type=OperationalEventType.INVENTORY_STOCK_UPDATED,
        event_category=OperationalEventCategory.INVENTORY,
        source_type=OperationalEventSourceType.MANUAL_UPLOAD,
        source_reference="manual_upload",
        occurred_at=datetime(2026, 5, 9, tzinfo=UTC),
        detected_at=datetime(2026, 5, 9, tzinfo=UTC),
        plant_reference=plant_reference,
        material_reference=material_reference,
        confidence_score=confidence_score,
        freshness_status=freshness_status,
    )


def only_type(candidates, risk_type: str):
    matches = [candidate for candidate in candidates if candidate.risk_type == risk_type]
    assert len(matches) == 1
    return matches[0]


def context_for(tenant: Tenant) -> RequestContext:
    return RequestContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        role="tenant_admin",
        user_id=1,
    )


def seed_rule_engine_data(db: Session) -> tuple[Tenant, Tenant]:
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    db.add_all([tenant_a, tenant_b])
    db.flush()
    plant_a = Plant(tenant_id=tenant_a.id, code="P1", name="Plant 1", location=None)
    material_a = Material(
        tenant_id=tenant_a.id,
        code="M1",
        name="Material 1",
        category="raw",
        uom="MT",
    )
    plant_b = Plant(tenant_id=tenant_b.id, code="P2", name="Plant 2", location=None)
    material_b = Material(
        tenant_id=tenant_b.id,
        code="M2",
        name="Material 2",
        category="raw",
        uom="MT",
    )
    db.add_all([plant_a, material_a, plant_b, material_b])
    db.flush()
    now = datetime(2026, 5, 9, 12, tzinfo=UTC)
    db.add(
        StockSnapshot(
            tenant_id=tenant_a.id,
            plant_id=plant_a.id,
            material_id=material_a.id,
            on_hand_mt=Decimal("20"),
            quality_held_mt=Decimal("0"),
            available_to_consume_mt=Decimal("20"),
            daily_consumption_mt=Decimal("10"),
            snapshot_time=now,
        )
    )
    db.add(
        StockSnapshot(
            tenant_id=tenant_b.id,
            plant_id=plant_b.id,
            material_id=material_b.id,
            on_hand_mt=Decimal("20"),
            quality_held_mt=Decimal("0"),
            available_to_consume_mt=Decimal("20"),
            daily_consumption_mt=Decimal("10"),
            snapshot_time=now,
        )
    )
    db.add(
        Shipment(
            tenant_id=tenant_a.id,
            shipment_id="SHIP-A",
            material_id=material_a.id,
            plant_id=plant_a.id,
            supplier_name="Supplier A",
            quantity_mt=Decimal("100"),
            planned_eta=now + timedelta(days=1),
            current_eta=now + timedelta(days=3),
            current_milestone="in_transit",
            last_tracking_update_at=now - timedelta(hours=8),
            current_state=ShipmentState.IN_TRANSIT,
            source_of_truth="manual_upload",
            latest_update_at=now - timedelta(hours=8),
        )
    )
    create_operational_event(
        db,
        event_payload(tenant_id=tenant_a.id, plant=plant_a, material=material_a),
    )
    create_operational_event(
        db,
        event_payload(tenant_id=tenant_b.id, plant=plant_b, material=material_b),
    )
    db.commit()
    assert db.scalar(select(OperationalEvent).where(OperationalEvent.tenant_id == tenant_a.id))
    return tenant_a, tenant_b


class seeded_rule_engine_session:
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
        tenant_a, tenant_b = seed_rule_engine_data(self.db)
        return self.db, tenant_a, tenant_b

    def __exit__(self, exc_type, exc_value, traceback):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)


def event_payload(*, tenant_id: int, plant: Plant, material: Material):
    from app.modules.operational_events.schemas import OperationalEventCreate

    return OperationalEventCreate(
        tenant_id=tenant_id,
        event_type=OperationalEventType.INVENTORY_STOCK_UPDATED,
        event_category=OperationalEventCategory.INVENTORY,
        source_type=OperationalEventSourceType.MANUAL_UPLOAD,
        source_reference="manual_upload",
        occurred_at=datetime(2026, 5, 1, tzinfo=UTC),
        detected_at=datetime(2026, 5, 9, tzinfo=UTC),
        plant_id=plant.id,
        plant_reference=plant.code,
        material_id=material.id,
        material_reference=material.code,
        quantity_value=Decimal("20"),
        quantity_unit="MT",
    )
