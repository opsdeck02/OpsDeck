from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    Material,
    MaterialProcessDependency,
    Plant,
    PlantMaterialThreshold,
    ProcessProductDependency,
    ProductionInterruptionImpactConfig,
    ProductionLine,
    Shipment,
    ShipmentInboundTrustConfig,
    StockSnapshot,
    Supplier,
    Tenant,
)
from app.models.enums import ShipmentState
from app.modules.impact.schemas import OperationalInterruptionImpact
from app.modules.rules.engine import RiskCandidate
from app.modules.signal_engine.service import list_signal_risks
from app.modules.stock.schemas import InventoryContinuityResult
from app.modules.trust.operational import (
    confidence_band,
    evaluate_configuration_completeness,
    evaluate_risk_operational_trust,
)
from app.schemas.context import RequestContext

NOW = datetime(2026, 5, 20, 12, tzinfo=UTC)


def test_fully_configured_context_returns_high_completeness() -> None:
    with managed_session() as db:
        ctx = seed_context(db, full=True)
        result = evaluate_configuration_completeness(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            inventory=inventory(confidence=Decimal("0.90")),
        )

        assert result.overall_completeness_score >= Decimal("85")
        assert result.operational_confidence_band == "high"
        assert result.completeness_by_area["product_process_dependency"] == Decimal("1.00")


def test_missing_interruption_config_lowers_completeness() -> None:
    with managed_session() as db:
        ctx = seed_context(db, full=True, interruption=False)
        result = evaluate_configuration_completeness(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            inventory=inventory(),
        )

        assert result.completeness_by_area["interruption_impact"] == Decimal("0.00")
        assert result.overall_completeness_score < Decimal("85")
        assert "Interruption impact assumptions are not configured." in result.missing_assumptions


def test_missing_process_dependency_lowers_trust() -> None:
    with managed_session() as db:
        ctx = seed_context(db, full=True, process_dependency=False)
        completeness = evaluate_configuration_completeness(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            inventory=inventory(),
        )
        trust = evaluate_risk_operational_trust(
            risk(impact=calculated_impact()),
            completeness,
            inventory=inventory(),
        )

        assert completeness.completeness_by_area["product_process_dependency"] == Decimal("0.00")
        assert any("No process dependency configured" in penalty for penalty in trust.trust_penalties)
        assert trust.risk_precision_band in {"moderate", "low"}


def test_missing_shipment_trust_config_lowers_completeness() -> None:
    with managed_session() as db:
        ctx = seed_context(db, full=True, shipment_trust=False)
        result = evaluate_configuration_completeness(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            inventory=inventory(),
        )

        assert result.completeness_by_area["shipment_inbound_trust"] == Decimal("0.00")
        assert "Shipment trust calibration is missing." in result.missing_assumptions


def test_fallback_interruption_economics_creates_trust_penalty() -> None:
    with managed_session() as db:
        ctx = seed_context(db, full=True)
        completeness = evaluate_configuration_completeness(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            inventory=inventory(),
        )
        trust = evaluate_risk_operational_trust(
            risk(impact=insufficient_config_impact()),
            completeness,
            inventory=inventory(),
        )

        assert any("Fallback interruption economics" in penalty for penalty in trust.trust_penalties)


def test_strong_visibility_confidence_boosts_trust() -> None:
    with managed_session() as db:
        ctx = seed_context(db, full=True)
        completeness = evaluate_configuration_completeness(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            inventory=inventory(confidence=Decimal("0.92")),
        )
        trust = evaluate_risk_operational_trust(
            risk(impact=calculated_impact()),
            completeness,
            inventory=inventory(confidence=Decimal("0.92")),
        )

        assert "Strong visibility confidence supports operational reasoning." in trust.trust_boosts


def test_weak_inbound_visibility_lowers_trust() -> None:
    with managed_session() as db:
        ctx = seed_context(db, full=True)
        weak_inventory = inventory(confidence=Decimal("0.30"), uncertain=Decimal("80"))
        completeness = evaluate_configuration_completeness(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            inventory=weak_inventory,
        )
        trust = evaluate_risk_operational_trust(
            risk(impact=calculated_impact()),
            completeness,
            inventory=weak_inventory,
        )

        assert any("Weak inbound visibility" in penalty for penalty in trust.trust_penalties)
        assert any("Visibility uncertainty" in penalty for penalty in trust.trust_penalties)


def test_supplier_context_fallback_lowers_trust_moderately() -> None:
    with managed_session() as db:
        ctx = seed_context(db, full=True, supplier_samples=1)
        completeness = evaluate_configuration_completeness(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            inventory=inventory(),
        )
        trust = evaluate_risk_operational_trust(
            risk(impact=calculated_impact()),
            completeness,
            inventory=inventory(),
        )

        assert completeness.completeness_by_area["supplier_context"] == Decimal("0.50")
        assert any("Supplier-context evidence insufficient" in penalty for penalty in trust.trust_penalties)


def test_risk_still_generates_with_low_trust() -> None:
    with managed_session() as db:
        ctx = seed_context(db, full=False)
        db.add(
            StockSnapshot(
                tenant_id=ctx.tenant.id,
                plant_id=ctx.plant.id,
                material_id=ctx.material.id,
                on_hand_mt=Decimal("10"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("10"),
                daily_consumption_mt=Decimal("10"),
                snapshot_time=NOW,
            )
        )
        db.commit()

        risks = list_signal_risks(db, request_context(ctx.tenant), now=NOW)

        assert risks
        selected = risks[0]
        assert selected.configuration_completeness is not None
        assert selected.operational_trust is not None
        assert selected.operational_trust.risk_precision_band in {"low", "unknown"}


def test_explainability_contains_penalties_and_boosts() -> None:
    with managed_session() as db:
        ctx = seed_context(db, full=False)
        db.add(
            StockSnapshot(
                tenant_id=ctx.tenant.id,
                plant_id=ctx.plant.id,
                material_id=ctx.material.id,
                on_hand_mt=Decimal("10"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("10"),
                daily_consumption_mt=Decimal("10"),
                snapshot_time=NOW,
            )
        )
        db.commit()

        selected = list_signal_risks(db, request_context(ctx.tenant), now=NOW)[0]

        assert selected.explainability is not None
        reason_chain = " ".join(selected.explainability.reason_chain)
        assert "Operational trust score" in reason_chain
        assert "Interruption impact assumptions are not configured" in reason_chain


def test_completeness_bands_map_correctly() -> None:
    assert confidence_band(Decimal("85")) == "high"
    assert confidence_band(Decimal("65")) == "moderate"
    assert confidence_band(Decimal("40")) == "low"
    assert confidence_band(Decimal("39.99")) == "unknown"


def test_tenant_isolation_for_completeness() -> None:
    with managed_session() as db:
        tenant_a = seed_context(db, full=True)
        tenant_b = seed_context(db, tenant_name="Tenant B", slug="tenant-b", full=False)

        result = evaluate_configuration_completeness(
            db,
            tenant_id=tenant_b.tenant.id,
            plant_id=tenant_b.plant.id,
            material_id=tenant_b.material.id,
            inventory=inventory(),
        )

        assert tenant_a.tenant.id != tenant_b.tenant.id
        assert result.completeness_by_area["continuity_thresholds"] == Decimal("0.00")
        assert result.completeness_by_area["interruption_impact"] == Decimal("0.00")


class Context:
    def __init__(self, tenant: Tenant, plant: Plant, material: Material, supplier: Supplier):
        self.tenant = tenant
        self.plant = plant
        self.material = material
        self.supplier = supplier


def managed_session():
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


def seed_context(
    db: Session,
    *,
    tenant_name: str = "Tenant",
    slug: str = "tenant",
    full: bool,
    interruption: bool = True,
    process_dependency: bool = True,
    shipment_trust: bool = True,
    supplier_samples: int = 3,
) -> Context:
    tenant = Tenant(name=tenant_name, slug=slug)
    db.add(tenant)
    db.flush()
    plant = Plant(tenant_id=tenant.id, code=f"P{tenant.id}", name="Plant", location="IN")
    material = Material(tenant_id=tenant.id, code=f"M{tenant.id}", name="Material", category="raw", uom="MT")
    supplier = Supplier(tenant_id=tenant.id, name="Supplier", code=f"SUP{tenant.id}")
    db.add_all([plant, material, supplier])
    db.flush()
    if full:
        db.add(
            PlantMaterialThreshold(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                warning_days=Decimal("14"),
                threshold_days=Decimal("7"),
            )
        )
    if full and interruption:
        db.add(
            ProductionInterruptionImpactConfig(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                production_line_id=None,
                production_rate_mt_per_hour=Decimal("120"),
                finished_goods_value_per_mt=Decimal("70000"),
                survivable_hours_without_material=Decimal("4"),
                line_dependency_ratio=Decimal("0.90"),
                downtime_cost_per_hour=Decimal("200000"),
                restart_cost=Decimal("5000000"),
                restart_time_hours=Decimal("6"),
                substitution_factor=Decimal("0.10"),
                cascading_impact_factor=Decimal("1.25"),
                currency="INR",
                is_active=True,
            )
        )
    if full and process_dependency:
        line = ProductionLine(
            tenant_id=tenant.id,
            plant_id=plant.id,
            code="BF-1",
            name="Blast Furnace 1",
            is_active=True,
        )
        db.add(line)
        db.flush()
        db.add(
            MaterialProcessDependency(
                tenant_id=tenant.id,
                material_id=material.id,
                process_id=line.id,
                dependency_ratio=Decimal("0.90"),
                is_active=True,
            )
        )
        db.add(
            ProcessProductDependency(
                tenant_id=tenant.id,
                process_id=line.id,
                product_name="HRC Coil",
                output_share_ratio=Decimal("1.00"),
                product_value_per_mt=Decimal("72000"),
                operational_criticality_factor=Decimal("1.25"),
                is_active=True,
            )
        )
    if full and shipment_trust:
        db.add(
            ShipmentInboundTrustConfig(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                visibility_profile="ocean",
                expected_visibility_cadence_hours=Decimal("72"),
                eta_drift_tolerance_hours=Decimal("24"),
                weak_visibility_threshold=Decimal("0.50"),
                is_active=True,
            )
        )
    for index in range(supplier_samples if full else 0):
        db.add(
            Shipment(
                tenant_id=tenant.id,
                shipment_id=f"S{tenant.id}-{index}",
                plant_id=plant.id,
                material_id=material.id,
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                quantity_mt=Decimal("100"),
                planned_eta=NOW + timedelta(days=2),
                current_eta=NOW + timedelta(days=2),
                current_state=ShipmentState.IN_TRANSIT,
                current_milestone="in_transit",
                source_of_truth="manual_upload",
                latest_update_at=NOW,
            )
        )
    db.commit()
    return Context(tenant, plant, material, supplier)


def inventory(
    *,
    confidence: Decimal = Decimal("0.90"),
    uncertain: Decimal = Decimal("0"),
):
    return InventoryContinuityResult(
        plant_reference="P1",
        material_reference="M1",
        on_hand_quantity=Decimal("100"),
        reserved_quantity=Decimal("0"),
        blocked_quantity=Decimal("0"),
        quality_hold_quantity=Decimal("0"),
        usable_quantity=Decimal("100"),
        inbound_committed_quantity=Decimal("100"),
        inbound_uncertain_quantity=uncertain,
        daily_consumption_rate=Decimal("10"),
        days_of_cover=Decimal("10"),
        raw_days_of_cover=Decimal("10"),
        physical_inbound_quantity_mt=Decimal("100"),
        trusted_inbound_protection_mt=Decimal("100") - uncertain,
        visibility_uncertain_quantity_mt=uncertain,
        visibility_confidence=confidence,
        trusted_inbound_quantity=Decimal("100") - uncertain,
        uncertain_inbound_quantity=uncertain,
        trusted_days_of_cover=Decimal("20") - (uncertain / Decimal("10")),
        projected_exhaustion_date=NOW + timedelta(days=10),
        cover_confidence_score=confidence,
        freshness_status="fresh",
        trust_warnings=[],
        visibility_reason_chain=[],
        unit="MT",
        calculation_reasons=["test continuity result"],
    )


def risk(impact: OperationalInterruptionImpact | None = None) -> RiskCandidate:
    return RiskCandidate(
        risk_type="days_of_cover_breach",
        severity="high",
        plant_reference="P1",
        material_reference="M1",
        days_of_cover=Decimal("2"),
        rule_reasons=["Configured critical threshold used."],
        operational_interruption_impact=impact,
    )


def request_context(tenant: Tenant) -> RequestContext:
    return RequestContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        role="tenant_admin",
        user_id=1,
    )


def calculated_impact() -> OperationalInterruptionImpact:
    return OperationalInterruptionImpact(
        material_exposure_value=Decimal("100000"),
        operational_interruption_impact=Decimal("500000"),
        calculation_status="calculated",
        currency="INR",
        missing_config_fields=[],
        formula_version="v1",
        reason_chain=["calculated"],
    )


def insufficient_config_impact() -> OperationalInterruptionImpact:
    return OperationalInterruptionImpact(
        material_exposure_value=Decimal("100000"),
        operational_interruption_impact=None,
        calculation_status="insufficient_config",
        currency="INR",
        missing_config_fields=["interruption_config"],
        formula_version="v1",
        reason_chain=["insufficient_config"],
    )
