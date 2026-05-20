from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Material, Plant, Shipment, StockSnapshot, Supplier, Tenant
from app.models.enums import ShipmentState
from app.modules.shipments.visibility_confidence import calculate_visibility_confidence
from app.modules.stock.continuity import calculate_inventory_continuity_for
from app.modules.suppliers.reliability_context import (
    calculate_supplier_reliability_context,
    reliability_band,
)
from app.schemas.context import RequestContext

NOW = datetime(2026, 5, 20, 12, tzinfo=UTC)


def test_same_supplier_material_plant_evidence_is_preferred() -> None:
    with reliability_test_session() as db:
        ctx = seed_context(db)
        seed_supplier_samples(db, ctx, plant=ctx.plant, material=ctx.material, count=3)
        seed_supplier_samples(
            db,
            ctx,
            plant=ctx.other_plant,
            material=ctx.material,
            count=3,
            late_hours=24,
        )

        result = calculate_supplier_reliability_context(
            db,
            tenant_id=ctx.tenant.id,
            shipment=current_shipment(ctx),
            now=NOW,
        )

        assert result.reliability_scope == "supplier_material_plant"
        assert result.sample_size == 3
        assert "plant" in result.reliability_context_key


def test_supplier_material_fallback_is_used_when_plant_context_missing() -> None:
    with reliability_test_session() as db:
        ctx = seed_context(db)
        seed_supplier_samples(db, ctx, plant=ctx.other_plant, material=ctx.material, count=3)

        result = calculate_supplier_reliability_context(
            db,
            tenant_id=ctx.tenant.id,
            shipment=current_shipment(ctx),
            now=NOW,
        )

        assert result.reliability_scope == "supplier_material"
        assert result.sample_size == 3


def test_supplier_global_fallback_is_used_when_material_context_missing() -> None:
    with reliability_test_session() as db:
        ctx = seed_context(db)
        seed_supplier_samples(db, ctx, plant=ctx.other_plant, material=ctx.other_material, count=3)

        result = calculate_supplier_reliability_context(
            db,
            tenant_id=ctx.tenant.id,
            shipment=current_shipment(ctx),
            now=NOW,
        )

        assert result.reliability_scope == "supplier_global"
        assert result.sample_size == 3


def test_missing_supplier_returns_unknown_safely() -> None:
    with reliability_test_session() as db:
        ctx = seed_context(db)
        shipment = current_shipment(ctx, supplier_id=None)

        result = calculate_supplier_reliability_context(
            db,
            tenant_id=ctx.tenant.id,
            shipment=shipment,
            now=NOW,
        )

        assert result.reliability_scope == "unknown"
        assert result.reliability_band == "unknown"
        assert result.contextual_reliability_score == Decimal("0.50")


def test_low_sample_uses_neutral_score_with_low_confidence() -> None:
    with reliability_test_session() as db:
        ctx = seed_context(db)
        seed_supplier_samples(db, ctx, plant=ctx.plant, material=ctx.material, count=1)

        result = calculate_supplier_reliability_context(
            db,
            tenant_id=ctx.tenant.id,
            shipment=current_shipment(ctx),
            now=NOW,
        )

        assert result.sample_size == 1
        assert result.contextual_reliability_score == Decimal("0.70")
        assert result.confidence_in_score == "low"
        assert any("neutral reliability" in reason for reason in result.reason_chain)


def test_ocean_eta_tolerance_prevents_unfair_supplier_penalty_for_small_drift() -> None:
    with reliability_test_session() as db:
        ctx = seed_context(db)
        seed_supplier_samples(db, ctx, plant=ctx.plant, material=ctx.material, count=1)
        ocean = current_shipment(
            ctx,
            vessel_name="MV Context",
            planned_eta=NOW + timedelta(days=5),
            current_eta=NOW + timedelta(days=5, hours=12),
        )

        result = calculate_supplier_reliability_context(
            db,
            tenant_id=ctx.tenant.id,
            shipment=ocean,
            visibility_result=calculate_visibility_confidence(ocean, now=NOW),
            now=NOW,
        )

        assert result.eta_behavior_penalty == Decimal("0.00")
        assert result.reliability_band == "acceptable"


def test_inland_eta_drift_penalizes_reliability_more_strictly() -> None:
    with reliability_test_session() as db:
        ctx = seed_context(db)
        seed_supplier_samples(db, ctx, plant=ctx.plant, material=ctx.material, count=1)
        inland = current_shipment(
            ctx,
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
            planned_eta=NOW + timedelta(days=1),
            current_eta=NOW + timedelta(days=1, hours=12),
        )

        result = calculate_supplier_reliability_context(
            db,
            tenant_id=ctx.tenant.id,
            shipment=inland,
            visibility_result=calculate_visibility_confidence(inland, now=NOW),
            now=NOW,
        )

        assert result.eta_behavior_penalty == Decimal("-0.10")
        assert result.contextual_reliability_score == Decimal("0.60")


def test_weak_visibility_confidence_lowers_reliability_slightly() -> None:
    with reliability_test_session() as db:
        ctx = seed_context(db)
        seed_supplier_samples(db, ctx, plant=ctx.plant, material=ctx.material, count=1)
        weak_visibility = current_shipment(
            ctx,
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
            latest_update_at=NOW - timedelta(hours=24),
        )

        result = calculate_supplier_reliability_context(
            db,
            tenant_id=ctx.tenant.id,
            shipment=weak_visibility,
            visibility_result=calculate_visibility_confidence(weak_visibility, now=NOW),
            now=NOW,
        )

        assert result.visibility_confidence_penalty == Decimal("-0.10")
        assert result.contextual_reliability_score == Decimal("0.60")


def test_abnormal_shipment_state_lowers_reliability() -> None:
    with reliability_test_session() as db:
        ctx = seed_context(db)
        seed_supplier_samples(db, ctx, plant=ctx.plant, material=ctx.material, count=1)
        delayed = current_shipment(ctx, current_state=ShipmentState.DELAYED)

        result = calculate_supplier_reliability_context(
            db,
            tenant_id=ctx.tenant.id,
            shipment=delayed,
            visibility_result=calculate_visibility_confidence(delayed, now=NOW),
            now=NOW,
        )

        assert result.contextual_reliability_score < Decimal("0.70")
        assert any("Abnormal current shipment state" in reason for reason in result.reason_chain)


def test_reliability_band_mapping() -> None:
    assert reliability_band(Decimal("0.85")) == "strong"
    assert reliability_band(Decimal("0.70")) == "acceptable"
    assert reliability_band(Decimal("0.50")) == "watch"
    assert reliability_band(Decimal("0.49")) == "weak"


def test_supplier_modifier_does_not_change_physical_inbound_quantity() -> None:
    with reliability_test_session() as db:
        ctx = seed_context(db)
        seed_supplier_samples(
            db,
            ctx,
            plant=ctx.plant,
            material=ctx.material,
            count=3,
            late_hours=48,
            latest_update_at=NOW - timedelta(hours=48),
        )
        db.add(
            StockSnapshot(
                tenant_id=ctx.tenant.id,
                plant_id=ctx.plant.id,
                material_id=ctx.material.id,
                on_hand_mt=Decimal("50"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("50"),
                daily_consumption_mt=Decimal("10"),
                snapshot_time=NOW,
            )
        )
        db.add(current_shipment(ctx, shipment_id="CURRENT-INBOUND", quantity_mt=Decimal("100")))
        db.commit()

        result = calculate_inventory_continuity_for(
            db,
            RequestContext(
                tenant_id=ctx.tenant.id,
                tenant_slug=ctx.tenant.slug,
                role="tenant_admin",
                user_id=1,
            ),
            ctx.plant.id,
            ctx.material.id,
            now=NOW,
        )

        assert result is not None
        assert result.physical_inbound_quantity_mt == Decimal("400.00")
        assert result.trusted_inbound_quantity < result.physical_inbound_quantity_mt


def test_explainability_includes_scope_sample_and_reasons() -> None:
    with reliability_test_session() as db:
        ctx = seed_context(db)
        seed_supplier_samples(db, ctx, plant=ctx.plant, material=ctx.material, count=3)

        result = calculate_supplier_reliability_context(
            db,
            tenant_id=ctx.tenant.id,
            shipment=current_shipment(ctx),
            now=NOW,
        )

        joined = " ".join(result.reason_chain)
        assert "supplier_material_plant" in joined
        assert "3 shipments" in joined
        assert "Final contextual supplier reliability band" in joined


def test_supplier_reliability_preserves_tenant_isolation() -> None:
    with reliability_test_session() as db:
        ctx = seed_context(db)
        other_tenant = Tenant(name="Tenant B", slug="tenant-b")
        db.add(other_tenant)
        db.flush()
        db.add(
            Shipment(
                tenant_id=other_tenant.id,
                shipment_id="OTHER-TENANT",
                plant_id=ctx.plant.id,
                material_id=ctx.material.id,
                supplier_id=ctx.supplier.id,
                supplier_name=ctx.supplier.name,
                quantity_mt=Decimal("100"),
                planned_eta=NOW + timedelta(days=1),
                current_eta=NOW + timedelta(days=5),
                current_state=ShipmentState.DELAYED,
                source_of_truth="manual_upload",
                latest_update_at=NOW - timedelta(days=5),
            )
        )
        seed_supplier_samples(db, ctx, plant=ctx.plant, material=ctx.material, count=1)

        result = calculate_supplier_reliability_context(
            db,
            tenant_id=ctx.tenant.id,
            shipment=current_shipment(ctx),
            now=NOW,
        )

        assert result.sample_size == 1
        assert result.contextual_reliability_score == Decimal("0.70")


class ReliabilityContext:
    def __init__(
        self,
        tenant: Tenant,
        plant: Plant,
        other_plant: Plant,
        material: Material,
        other_material: Material,
        supplier: Supplier,
    ) -> None:
        self.tenant = tenant
        self.plant = plant
        self.other_plant = other_plant
        self.material = material
        self.other_material = other_material
        self.supplier = supplier


def reliability_test_session():
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


def seed_context(db: Session) -> ReliabilityContext:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    db.add(tenant)
    db.flush()
    plant = Plant(tenant_id=tenant.id, code="P1", name="Plant 1", location="IN")
    other_plant = Plant(tenant_id=tenant.id, code="P2", name="Plant 2", location="IN")
    material = Material(tenant_id=tenant.id, code="COAL", name="Coal", category="raw")
    other_material = Material(tenant_id=tenant.id, code="LIME", name="Limestone", category="raw")
    supplier = Supplier(tenant_id=tenant.id, name="Context Supplier", code="CTX")
    db.add_all([plant, other_plant, material, other_material, supplier])
    db.flush()
    return ReliabilityContext(tenant, plant, other_plant, material, other_material, supplier)


def seed_supplier_samples(
    db: Session,
    ctx: ReliabilityContext,
    *,
    plant: Plant,
    material: Material,
    count: int,
    late_hours: int = 0,
    latest_update_at: datetime | None = None,
) -> None:
    for index in range(count):
        db.add(
            Shipment(
                tenant_id=ctx.tenant.id,
                shipment_id=f"SAMPLE-{plant.code}-{material.code}-{index}-{late_hours}",
                plant_id=plant.id,
                material_id=material.id,
                supplier_id=ctx.supplier.id,
                supplier_name=ctx.supplier.name,
                quantity_mt=Decimal("100"),
                planned_eta=NOW + timedelta(days=index + 1),
                current_eta=NOW + timedelta(days=index + 1, hours=late_hours),
                current_state=ShipmentState.IN_TRANSIT,
                current_milestone="in_transit",
                source_of_truth="manual_upload",
                latest_update_at=latest_update_at or NOW - timedelta(hours=2),
            )
        )
    db.flush()


def current_shipment(ctx: ReliabilityContext, **overrides) -> Shipment:
    values = {
        "tenant_id": ctx.tenant.id,
        "shipment_id": "CURRENT",
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
