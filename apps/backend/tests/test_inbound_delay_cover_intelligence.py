from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Material, Plant, Shipment, Supplier, Tenant
from app.models.enums import ShipmentState
from app.modules.rules.engine import evaluate_inbound_delay_against_cover
from app.modules.rules.inbound_delay_cover import evaluate_inbound_delay_cover_intelligence
from app.modules.shipments.continuity import calculate_shipment_continuity
from app.modules.stock.continuity import calculate_inventory_continuity

NOW = datetime(2026, 5, 20, 12, tzinfo=UTC)


def test_normal_cover_stable_eta_strong_trust_creates_no_inbound_delay_risk() -> None:
    with inbound_delay_session() as db:
        ctx = seed_context(db)
        shipment = shipment_model(ctx, vessel_name="MV Stable")
        inventory = make_inventory(days_of_cover=Decimal("20"), trusted_ratio=Decimal("0.90"))

        candidates = evaluate_inbound_delay_against_cover(
            shipment_continuity(shipment),
            inventory,
            db=db,
            tenant_id=ctx.tenant.id,
            shipment_model=shipment,
            now=NOW,
        )

        assert candidates == []


def test_warning_cover_degraded_eta_creates_high_risk() -> None:
    with inbound_delay_session() as db:
        ctx = seed_context(db)
        shipment = shipment_model(
            ctx,
            planned_eta=NOW + timedelta(days=1),
            current_eta=NOW + timedelta(days=2, hours=12),
        )

        candidate = only_candidate(
            evaluate_inbound_delay_against_cover(
                shipment_continuity(shipment),
                make_inventory(days_of_cover=Decimal("4"), trusted_ratio=Decimal("0.90")),
                db=db,
                tenant_id=ctx.tenant.id,
                shipment_model=shipment,
                now=NOW,
            )
        )

        assert candidate.severity == "high"
        assert any("ETA behavior status is degraded" in reason for reason in candidate.rule_reasons)


def test_critical_cover_weak_protection_degraded_eta_creates_critical_risk() -> None:
    with inbound_delay_session() as db:
        ctx = seed_context(db)
        shipment = shipment_model(
            ctx,
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
            planned_eta=NOW + timedelta(days=1),
            current_eta=NOW + timedelta(days=1, hours=12),
            latest_update_at=NOW - timedelta(hours=24),
        )

        result = evaluate_inbound_delay_cover_intelligence(
            shipment_continuity(shipment),
            make_inventory(days_of_cover=Decimal("1.5"), trusted_ratio=Decimal("0.40")),
            db=db,
            tenant_id=ctx.tenant.id,
            shipment=shipment,
            now=NOW,
        )

        assert result.severity == "critical"
        assert result.trusted_protection_weak is True
        assert result.applies is True


def test_delay_pushing_into_critical_threshold_creates_high_risk() -> None:
    with inbound_delay_session() as db:
        ctx = seed_context(db)
        shipment = shipment_model(
            ctx,
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
            planned_eta=NOW + timedelta(days=1),
            current_eta=NOW + timedelta(days=2),
        )

        result = evaluate_inbound_delay_cover_intelligence(
            shipment_continuity(shipment),
            make_inventory(
                days_of_cover=Decimal("3"),
                trusted_ratio=Decimal("0.40"),
                threshold_days=Decimal("2"),
                warning_days=Decimal("6"),
            ),
            db=db,
            tenant_id=ctx.tenant.id,
            shipment=shipment,
            now=NOW,
        )

        assert result.delay_exceeds_cover is False
        assert result.delay_exceeds_threshold_window is True
        assert result.severity == "high"


def test_ocean_stable_eta_and_normal_cadence_does_not_panic() -> None:
    with inbound_delay_session() as db:
        ctx = seed_context(db)
        shipment = shipment_model(
            ctx,
            vessel_name="MV Tolerant",
            planned_eta=NOW + timedelta(days=5),
            current_eta=NOW + timedelta(days=5, hours=12),
            latest_update_at=NOW - timedelta(hours=48),
        )

        result = evaluate_inbound_delay_cover_intelligence(
            shipment_continuity(shipment),
            make_inventory(days_of_cover=Decimal("20"), trusted_ratio=Decimal("0.90")),
            db=db,
            tenant_id=ctx.tenant.id,
            shipment=shipment,
            now=NOW,
        )

        assert result.applies is False
        assert result.severity == "none"


def test_inland_degraded_eta_and_weak_trust_escalates() -> None:
    with inbound_delay_session() as db:
        ctx = seed_context(db)
        shipment = shipment_model(
            ctx,
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
            planned_eta=NOW + timedelta(days=1),
            current_eta=NOW + timedelta(days=1, hours=12),
            latest_update_at=NOW - timedelta(hours=24),
        )

        result = evaluate_inbound_delay_cover_intelligence(
            shipment_continuity(shipment),
            make_inventory(days_of_cover=Decimal("4"), trusted_ratio=Decimal("0.40")),
            db=db,
            tenant_id=ctx.tenant.id,
            shipment=shipment,
            now=NOW,
        )

        assert result.severity == "high"
        assert result.eta_behavior_status == "degraded"
        assert result.trusted_protection_weak is True


def test_physical_inbound_quantity_remains_unchanged_in_output_and_reason() -> None:
    with inbound_delay_session() as db:
        ctx = seed_context(db)
        shipment = shipment_model(ctx, quantity_mt=Decimal("125"))

        result = evaluate_inbound_delay_cover_intelligence(
            shipment_continuity(shipment),
            make_inventory(
                days_of_cover=Decimal("4"), physical=Decimal("125"), trusted_ratio=Decimal("0.40")
            ),
            db=db,
            tenant_id=ctx.tenant.id,
            shipment=shipment,
            now=NOW,
        )

        assert result.physical_inbound_quantity_mt == Decimal("125.00")
        assert any(
            "Physical inbound quantity remains unchanged" in reason
            for reason in result.reason_chain
        )


def test_trusted_protection_weak_influences_severity() -> None:
    with inbound_delay_session() as db:
        ctx = seed_context(db)
        shipment = shipment_model(
            ctx,
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
            latest_update_at=NOW - timedelta(hours=24),
        )

        result = evaluate_inbound_delay_cover_intelligence(
            shipment_continuity(shipment),
            make_inventory(days_of_cover=Decimal("20"), trusted_ratio=Decimal("0.40")),
            db=db,
            tenant_id=ctx.tenant.id,
            shipment=shipment,
            now=NOW,
        )

        assert result.trusted_protection_weak is True
        assert result.severity == "medium"


def test_configured_thresholds_are_used_instead_of_hardcoded_five_day_logic() -> None:
    with inbound_delay_session() as db:
        ctx = seed_context(db)
        shipment = shipment_model(
            ctx,
            planned_eta=NOW + timedelta(days=1),
            current_eta=NOW + timedelta(days=2),
        )

        result = evaluate_inbound_delay_cover_intelligence(
            shipment_continuity(shipment),
            make_inventory(
                days_of_cover=Decimal("20"),
                trusted_ratio=Decimal("0.90"),
                threshold_days=Decimal("15"),
                warning_days=Decimal("30"),
            ),
            db=db,
            tenant_id=ctx.tenant.id,
            shipment=shipment,
            now=NOW,
        )

        assert result.severity == "high"
        assert any(
            "Configured warning threshold used: 30.00 days" in reason
            for reason in result.reason_chain
        )


def test_missing_config_preserves_fallback_threshold_behavior() -> None:
    result = evaluate_inbound_delay_cover_intelligence(
        degraded_shipment_continuity(eta_slip_days=Decimal("1")),
        make_inventory(days_of_cover=Decimal("4"), trusted_ratio=Decimal("0.90")),
        now=NOW,
    )

    assert result.severity == "high"
    assert any(
        "Fallback warning threshold used: 5 days" in reason for reason in result.reason_chain
    )


def test_weak_supplier_reliability_increases_concern_if_already_risky() -> None:
    with inbound_delay_session() as db:
        ctx = seed_context(db)
        seed_weak_supplier_history(db, ctx)
        shipment = shipment_model(
            ctx,
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
            planned_eta=NOW + timedelta(days=1),
            current_eta=NOW + timedelta(days=1, hours=6),
        )

        result = evaluate_inbound_delay_cover_intelligence(
            shipment_continuity(shipment),
            make_inventory(days_of_cover=Decimal("20"), trusted_ratio=Decimal("0.90")),
            db=db,
            tenant_id=ctx.tenant.id,
            shipment=shipment,
            now=NOW,
        )

        assert result.supplier_reliability_band == "weak"
        assert result.severity == "high"
        assert any(
            "Weak supplier reliability increased concern" in reason
            for reason in result.reason_chain
        )


def test_reason_chain_includes_physical_vs_trusted_protection_distinction() -> None:
    result = evaluate_inbound_delay_cover_intelligence(
        degraded_shipment_continuity(eta_slip_days=Decimal("1")),
        make_inventory(days_of_cover=Decimal("4"), trusted_ratio=Decimal("0.40")),
        now=NOW,
    )

    joined = " ".join(result.reason_chain)
    assert "Physical inbound quantity remains unchanged" in joined
    assert "trusted inbound protection" in joined
    assert "not missing material" in joined


class InboundDelayContext:
    def __init__(
        self, tenant: Tenant, plant: Plant, material: Material, supplier: Supplier
    ) -> None:
        self.tenant = tenant
        self.plant = plant
        self.material = material
        self.supplier = supplier


def inbound_delay_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    class ManagedSession:
        def __enter__(self) -> Session:
            self.db = SessionLocal()
            return self.db

        def __exit__(self, exc_type, exc, tb) -> None:
            self.db.close()
            Base.metadata.drop_all(bind=engine)

    return ManagedSession()


def seed_context(db: Session) -> InboundDelayContext:
    tenant = Tenant(name="Tenant", slug="tenant")
    db.add(tenant)
    db.flush()
    plant = Plant(tenant_id=tenant.id, code="P1", name="Plant 1", location="IN")
    material = Material(tenant_id=tenant.id, code="M1", name="Material 1", category="raw")
    supplier = Supplier(tenant_id=tenant.id, name="Supplier 1", code="SUP1")
    db.add_all([plant, material, supplier])
    db.flush()
    return InboundDelayContext(tenant, plant, material, supplier)


def make_inventory(
    *,
    days_of_cover: Decimal,
    trusted_ratio: Decimal,
    physical: Decimal = Decimal("100"),
    threshold_days: Decimal | None = None,
    warning_days: Decimal | None = None,
):
    daily_consumption = Decimal("10")
    trusted = (physical * trusted_ratio).quantize(Decimal("0.01"))
    uncertain = physical - trusted
    return calculate_inventory_continuity(
        plant_reference="P1",
        material_reference="M1",
        on_hand_quantity=days_of_cover * daily_consumption,
        daily_consumption_rate=daily_consumption,
        inbound_committed_quantity=physical,
        trusted_inbound_quantity=trusted,
        uncertain_inbound_quantity=uncertain,
        physical_inbound_quantity_mt=physical,
        trusted_inbound_protection_mt=trusted,
        visibility_uncertain_quantity_mt=uncertain,
        threshold_days=threshold_days,
        warning_days=warning_days,
        unit="MT",
        now=NOW,
    )


def shipment_model(ctx: InboundDelayContext, **overrides) -> Shipment:
    values = {
        "tenant_id": ctx.tenant.id,
        "shipment_id": "SHIP-1",
        "plant_id": ctx.plant.id,
        "material_id": ctx.material.id,
        "supplier_id": ctx.supplier.id,
        "supplier_name": ctx.supplier.name,
        "quantity_mt": Decimal("100"),
        "planned_eta": NOW + timedelta(days=2),
        "current_eta": NOW + timedelta(days=2),
        "current_state": ShipmentState.IN_TRANSIT,
        "current_milestone": "in_transit",
        "source_of_truth": "manual_upload",
        "latest_update_at": NOW - timedelta(hours=2),
    }
    values.update(overrides)
    return Shipment(**values)


def shipment_continuity(shipment: Shipment):
    return calculate_shipment_continuity(
        shipment_reference=shipment.shipment_id,
        eta=shipment.current_eta,
        previous_eta=shipment.latest_eta,
        planned_eta=shipment.planned_eta,
        current_milestone=shipment.current_milestone,
        tracking_updated_at=shipment.latest_update_at,
        linked_purchase_order_reference="PO-1",
        linked_material_reference="M1",
        linked_plant_reference="P1",
        current_state=shipment.current_state,
        now=NOW,
    )


def degraded_shipment_continuity(eta_slip_days: Decimal):
    previous_eta = NOW + timedelta(days=1)
    return calculate_shipment_continuity(
        shipment_reference="SHIP-1",
        eta=previous_eta + timedelta(days=float(eta_slip_days)),
        previous_eta=previous_eta,
        current_milestone="in_transit",
        tracking_updated_at=NOW - timedelta(hours=8),
        linked_purchase_order_reference="PO-1",
        linked_material_reference="M1",
        linked_plant_reference="P1",
        current_state=ShipmentState.IN_TRANSIT,
        now=NOW,
    )


def seed_weak_supplier_history(db: Session, ctx: InboundDelayContext) -> None:
    for index in range(3):
        db.add(
            Shipment(
                tenant_id=ctx.tenant.id,
                shipment_id=f"WEAK-{index}",
                plant_id=ctx.plant.id,
                material_id=ctx.material.id,
                supplier_id=ctx.supplier.id,
                supplier_name=ctx.supplier.name,
                quantity_mt=Decimal("100"),
                planned_eta=NOW + timedelta(days=index + 1),
                current_eta=NOW + timedelta(days=index + 3),
                current_state=ShipmentState.INLAND_TRANSIT,
                current_milestone="truck dispatched",
                source_of_truth="manual_upload",
                latest_update_at=NOW - timedelta(hours=24),
            )
        )
    db.flush()


def only_candidate(candidates):
    assert len(candidates) == 1
    return candidates[0]
