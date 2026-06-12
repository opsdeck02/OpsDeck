from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    Material,
    MaterialProcessDependency,
    Plant,
    ProcessProductDependency,
    ProductionInterruptionImpactConfig,
    ProductionLine,
    Shipment,
    StockSnapshot,
    Supplier,
    Tenant,
)
from app.models.enums import ShipmentState
from app.modules.impact.production_interruption import (
    ProductionInterruptionInputs,
    calculate_production_interruption_impact,
)
from app.modules.recommendations.operational_actions import recommend_operational_actions
from app.modules.rules.engine import RiskCandidate, evaluate_inventory_rules
from app.modules.rules.inbound_delay_cover import evaluate_inbound_delay_cover_intelligence
from app.modules.shipments.continuity import calculate_shipment_continuity
from app.modules.shipments.visibility_confidence import calculate_visibility_confidence
from app.modules.signal_engine.service import list_signal_risks
from app.modules.stock.continuity import calculate_inventory_continuity
from app.modules.trust.operational import (
    evaluate_configuration_completeness,
    evaluate_risk_operational_trust,
)
from app.schemas.context import RequestContext

NOW = datetime(2026, 5, 20, 12, tzinfo=UTC)
FORBIDDEN_ACTION_TERMS = {"reorder", "buy material", "place order", "approve po"}


def test_ocean_shipment_stable_visibility_does_not_panic() -> None:
    shipment = shipment_model(
        vessel_name="MV Pilot Ocean",
        planned_eta=NOW + timedelta(days=5),
        current_eta=NOW + timedelta(days=5),
        latest_update_at=NOW - timedelta(hours=48),
        current_state=ShipmentState.IN_TRANSIT,
        current_milestone="on_water",
    )

    visibility = calculate_visibility_confidence(shipment, now=NOW)
    inventory = inventory_result(days_of_cover=Decimal("20"), visibility=visibility)
    continuity = shipment_continuity(shipment)
    delay_result = evaluate_inbound_delay_cover_intelligence(
        continuity,
        inventory,
        shipment=shipment,
        now=NOW,
    )
    actions = recommend_operational_actions(
        risk_from_delay(delay_result, severity="low"),
        inventory=inventory,
    )

    assert visibility.visibility_profile == "ocean"
    assert visibility.visibility_confidence >= Decimal("0.85")
    assert visibility.trusted_inbound_protection_mt >= Decimal("85.00")
    assert delay_result.applies is False
    assert {action.action_type for action in actions} == {"monitor"}
    assert_no_procurement_actions(actions)


def test_inland_shipment_degraded_escalates_when_cover_is_tight() -> None:
    shipment = shipment_model(
        vessel_name=None,
        current_state=ShipmentState.INLAND_TRANSIT,
        current_milestone="near_plant gate_in blocked exception",
        planned_eta=NOW + timedelta(days=1),
        current_eta=NOW + timedelta(days=1, hours=12),
        latest_update_at=NOW - timedelta(hours=24),
        last_tracking_update_at=NOW - timedelta(hours=24),
    )

    visibility = calculate_visibility_confidence(shipment, now=NOW)
    inventory = inventory_result(days_of_cover=Decimal("4"), visibility=visibility)
    continuity = shipment_continuity(shipment)
    delay_result = evaluate_inbound_delay_cover_intelligence(
        continuity,
        inventory,
        shipment=shipment,
        now=NOW,
    )
    actions = recommend_operational_actions(
        SimpleNamespace(
            risk_type=delay_result.risk_type,
            severity=delay_result.severity,
            days_of_cover=delay_result.days_of_cover,
            rule_reasons=[
                *visibility.reason_chain,
                *delay_result.reason_chain,
                "near_plant gate_in milestone.",
            ],
            operational_interruption_impact=None,
        ),
        inventory=inventory,
        shipment=continuity,
    )

    assert visibility.visibility_profile == "inland"
    assert visibility.eta_behavior_status in {"degraded", "volatile"}
    assert visibility.visibility_confidence <= Decimal("0.50")
    assert delay_result.severity == "high"
    assert delay_result.trusted_protection_weak is True
    assert "confirm_inland_movement" in {action.action_type for action in actions}


def test_imported_critical_material_uses_configured_early_warning_thresholds() -> None:
    inventory = inventory_result(
        days_of_cover=Decimal("30"),
        threshold_days=Decimal("15"),
        warning_days=Decimal("60"),
        physical=Decimal("0"),
        trusted=Decimal("0"),
        uncertain=Decimal("0"),
    )

    candidate = one_risk(evaluate_inventory_rules(inventory, now=NOW), "days_of_cover_breach")

    assert candidate.severity == "medium"
    assert any(
        "configured warning threshold of 60.00 days" in reason
        for reason in candidate.rule_reasons
    )


def test_protected_reserve_breach_creates_reserve_warning() -> None:
    inventory = inventory_result(
        days_of_cover=Decimal("8"),
        threshold_days=Decimal("3"),
        warning_days=Decimal("5"),
        minimum_buffer_stock_days=Decimal("10"),
        minimum_buffer_stock_mt=Decimal("90"),
        on_hand=Decimal("80"),
        physical=Decimal("0"),
        trusted=Decimal("0"),
        uncertain=Decimal("0"),
    )

    risks = evaluate_inventory_rules(inventory, now=NOW)
    assert not any(risk.risk_type == "days_of_cover_breach" for risk in risks)
    candidate = one_risk(risks, "protected_reserve_breach")

    assert candidate.severity == "medium"
    assert any(
        "Protected reserve days threshold was breached" in reason
        for reason in candidate.rule_reasons
    )
    assert any(
        "Protected reserve quantity threshold was breached" in reason
        for reason in candidate.rule_reasons
    )


def test_physical_inbound_exists_but_trusted_protection_is_weak() -> None:
    shipment = shipment_model(
        vessel_name=None,
        current_state=ShipmentState.INLAND_TRANSIT,
        current_milestone="truck dispatched",
        planned_eta=NOW + timedelta(days=1),
        current_eta=NOW + timedelta(days=1, hours=12),
        latest_update_at=NOW - timedelta(hours=24),
        quantity_mt=Decimal("500"),
    )

    visibility = calculate_visibility_confidence(shipment, now=NOW)
    inventory = inventory_result(days_of_cover=Decimal("6"), visibility=visibility)
    delay_result = evaluate_inbound_delay_cover_intelligence(
        shipment_continuity(shipment),
        inventory,
        shipment=shipment,
        now=NOW,
    )
    actions = recommend_operational_actions(risk_from_delay(delay_result), inventory=inventory)

    assert delay_result.physical_inbound_quantity_mt == Decimal("500.00")
    assert delay_result.trusted_inbound_protection_mt < delay_result.physical_inbound_quantity_mt
    assert delay_result.visibility_uncertain_quantity_mt == (
        delay_result.physical_inbound_quantity_mt - delay_result.trusted_inbound_protection_mt
    )
    assert "verify_inbound" in {action.action_type for action in actions}
    assert any("not missing material" in reason for reason in delay_result.reason_chain)
    assert_no_procurement_actions(actions)


def test_product_process_dependency_impact_uses_product_mix_not_blended_fallback() -> None:
    with managed_session() as db:
        ctx = seed_context(db)
        config = interruption_config(ctx, substitution_factor=Decimal("0.00"))
        db.add(config)
        seed_product_process_dependency(db, ctx, substitution_factor=Decimal("0.00"))
        db.commit()

        result = calculate_production_interruption_impact(
            impact_inputs(ctx, days_of_cover=Decimal("1"), risk_hours_remaining=Decimal("24")),
            config,
            db=db,
        )

        reasons = " ".join(result.reason_chain)
        assert result.calculation_status == "calculated"
        assert "Product and process dependency model used" in reasons
        assert "Blast Furnace 1 output mix" in reasons
        assert "fallback weighted output value" not in reasons


def test_missing_configuration_keeps_risk_but_marks_operational_trust_low() -> None:
    with managed_session() as db:
        ctx = seed_context(db)
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
        assert selected.operational_trust.reasoning_strength in {"partial", "weak"}
        assert selected.configuration_completeness.missing_assumptions


def test_substitution_reduces_product_process_interruption_impact() -> None:
    with managed_session() as db:
        ctx = seed_context(db)
        base_config = interruption_config(ctx, substitution_factor=Decimal("0.00"))
        substituted_config = interruption_config(ctx, substitution_factor=Decimal("0.75"))
        db.add(base_config)
        seed_product_process_dependency(db, ctx, substitution_factor=Decimal("0.75"))
        db.commit()
        inputs = impact_inputs(ctx, days_of_cover=Decimal("1"), risk_hours_remaining=Decimal("24"))

        base = calculate_production_interruption_impact(inputs, base_config, db=db)
        substituted = calculate_production_interruption_impact(inputs, substituted_config, db=db)

        assert substituted.final_estimated_impact < base.final_estimated_impact
        assert any(
            "effective process dependency after line/substitution weighting" in reason
            for reason in substituted.reason_chain
        )


def test_weak_supplier_context_mildly_reduces_trust_and_escalates_supplier() -> None:
    with managed_session() as db:
        ctx = seed_context(db)
        seed_weak_supplier_history(db, ctx)
        shipment = shipment_model(
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            supplier_id=ctx.supplier.id,
            supplier_name=ctx.supplier.name,
            vessel_name=None,
            current_state=ShipmentState.DELAYED,
            current_milestone="truck delayed exception",
            planned_eta=NOW + timedelta(days=1),
            current_eta=NOW + timedelta(days=1, hours=12),
            latest_eta=NOW + timedelta(days=1, hours=4),
            latest_update_at=NOW - timedelta(hours=16),
        )

        visibility = calculate_visibility_confidence(shipment, now=NOW)
        inventory = inventory_result(days_of_cover=Decimal("4"), visibility=visibility)
        result = evaluate_inbound_delay_cover_intelligence(
            shipment_continuity(shipment),
            inventory,
            db=db,
            tenant_id=ctx.tenant.id,
            shipment=shipment,
            now=NOW,
        )
        actions = recommend_operational_actions(
            SimpleNamespace(
                risk_type=result.risk_type,
                severity=result.severity,
                days_of_cover=result.days_of_cover,
                rule_reasons=[
                    *result.reason_chain,
                    "Abnormal current shipment state applied penalty.",
                ],
                operational_interruption_impact=None,
            ),
            inventory=inventory,
        )

        assert result.supplier_reliability_band == "weak"
        assert result.physical_inbound_quantity_mt == Decimal("100.00")
        assert result.trusted_inbound_protection_mt < visibility.trusted_inbound_protection_mt
        assert "escalate_supplier" in {action.action_type for action in actions}
        assert_no_procurement_actions(actions)


def test_scenario_pack_configuration_completeness_identifies_missing_assumptions() -> None:
    with managed_session() as db:
        ctx = seed_context(db)
        inventory = inventory_result(
            days_of_cover=Decimal("2"),
            physical=Decimal("0"),
            trusted=Decimal("0"),
            uncertain=Decimal("0"),
        )
        completeness = evaluate_configuration_completeness(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            inventory=inventory,
        )
        trust = evaluate_risk_operational_trust(
            RiskCandidate(
                risk_type="days_of_cover_breach",
                severity="high",
                plant_reference=ctx.plant.code,
                material_reference=ctx.material.code,
                days_of_cover=Decimal("2"),
                rule_reasons=["Continuity exposure detected."],
            ),
            completeness,
            inventory=inventory,
        )

        assert completeness.overall_completeness_score < Decimal("65")
        assert "Continuity thresholds are not configured." in completeness.missing_assumptions
        assert any("No process dependency configured" in item for item in trust.trust_penalties)


class PilotContext:
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


def seed_context(db: Session) -> PilotContext:
    tenant = Tenant(name="Pilot Steel", slug="pilot-steel")
    db.add(tenant)
    db.flush()
    plant = Plant(tenant_id=tenant.id, code="TATA_JSR_BF1", name="Jamshedpur BF1", location="IN")
    material = Material(
        tenant_id=tenant.id,
        code="COKING_COAL",
        name="Imported coking coal",
        category="raw",
        uom="MT",
    )
    supplier = Supplier(tenant_id=tenant.id, name="Eastern Bulk Logistics", code="EBL")
    db.add_all([plant, material, supplier])
    db.flush()
    return PilotContext(tenant, plant, material, supplier)


def request_context(tenant: Tenant) -> RequestContext:
    return RequestContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        role="tenant_admin",
        user_id=1,
    )


def shipment_model(**overrides) -> Shipment:
    values = {
        "tenant_id": 1,
        "shipment_id": "PILOT-SHIP-1",
        "plant_id": 1,
        "material_id": 1,
        "supplier_id": None,
        "supplier_name": "Eastern Bulk Logistics",
        "quantity_mt": Decimal("100"),
        "planned_eta": NOW + timedelta(days=2),
        "current_eta": NOW + timedelta(days=2),
        "latest_eta": None,
        "current_state": ShipmentState.IN_TRANSIT,
        "current_milestone": "in_transit",
        "source_of_truth": "manual_upload",
        "latest_update_at": NOW - timedelta(hours=2),
        "last_tracking_update_at": NOW - timedelta(hours=2),
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
        tracking_updated_at=shipment.last_tracking_update_at or shipment.latest_update_at,
        linked_purchase_order_reference="PO-PILOT-1",
        linked_material_reference="COKING_COAL",
        linked_plant_reference="TATA_JSR_BF1",
        current_state=shipment.current_state,
        now=NOW,
    )


def inventory_result(
    *,
    days_of_cover: Decimal,
    visibility=None,
    threshold_days: Decimal | None = Decimal("2"),
    warning_days: Decimal | None = Decimal("5"),
    minimum_buffer_stock_days: Decimal | None = None,
    minimum_buffer_stock_mt: Decimal | None = None,
    on_hand: Decimal | None = None,
    physical: Decimal | None = None,
    trusted: Decimal | None = None,
    uncertain: Decimal | None = None,
):
    if visibility is not None:
        physical = visibility.physical_inbound_quantity_mt
        trusted = visibility.trusted_inbound_protection_mt
        uncertain = visibility.visibility_uncertain_quantity_mt
    physical = Decimal("100") if physical is None else physical
    trusted = Decimal("90") if trusted is None else trusted
    uncertain = physical - trusted if uncertain is None else uncertain
    daily_consumption = Decimal("10")
    on_hand = days_of_cover * daily_consumption if on_hand is None else on_hand
    return calculate_inventory_continuity(
        plant_reference="TATA_JSR_BF1",
        material_reference="COKING_COAL",
        on_hand_quantity=on_hand,
        daily_consumption_rate=daily_consumption,
        inbound_committed_quantity=physical,
        trusted_inbound_quantity=trusted,
        uncertain_inbound_quantity=uncertain,
        physical_inbound_quantity_mt=physical,
        trusted_inbound_protection_mt=trusted,
        visibility_uncertain_quantity_mt=uncertain,
        threshold_days=threshold_days,
        warning_days=warning_days,
        minimum_buffer_stock_days=minimum_buffer_stock_days,
        minimum_buffer_stock_mt=minimum_buffer_stock_mt,
        cover_confidence_score=(
            visibility.visibility_confidence if visibility is not None else Decimal("0.90")
        ),
        visibility_reason_chain=visibility.reason_chain if visibility is not None else [],
        unit="MT",
        now=NOW,
    )


def risk_from_delay(result, *, severity: str | None = None):
    return SimpleNamespace(
        risk_type=result.risk_type,
        severity=severity or result.severity,
        days_of_cover=result.days_of_cover,
        rule_reasons=result.reason_chain,
        operational_interruption_impact=None,
    )


def one_risk(candidates: list[RiskCandidate], risk_type: str) -> RiskCandidate:
    matches = [candidate for candidate in candidates if candidate.risk_type == risk_type]
    assert len(matches) == 1
    return matches[0]


def interruption_config(
    ctx: PilotContext,
    *,
    substitution_factor: Decimal = Decimal("0.10"),
) -> ProductionInterruptionImpactConfig:
    return ProductionInterruptionImpactConfig(
        tenant_id=ctx.tenant.id,
        plant_id=ctx.plant.id,
        material_id=ctx.material.id,
        production_line_id=None,
        production_rate_mt_per_hour=Decimal("120"),
        finished_goods_value_per_mt=Decimal("70000"),
        survivable_hours_without_material=Decimal("4"),
        line_dependency_ratio=Decimal("0.90"),
        downtime_cost_per_hour=Decimal("200000"),
        restart_cost=Decimal("5000000"),
        restart_time_hours=Decimal("6"),
        substitution_factor=substitution_factor,
        cascading_impact_factor=Decimal("1.25"),
        currency="INR",
        is_active=True,
    )


def impact_inputs(
    ctx: PilotContext,
    *,
    days_of_cover: Decimal,
    risk_hours_remaining: Decimal,
) -> ProductionInterruptionInputs:
    return ProductionInterruptionInputs(
        tenant_id=ctx.tenant.id,
        plant_id=ctx.plant.id,
        material_id=ctx.material.id,
        material_exposure_value=Decimal("100000"),
        days_of_cover=days_of_cover,
        risk_hours_remaining=risk_hours_remaining,
        urgency_band="immediate",
        continuity_severity="critical",
        trusted_inbound_ratio=Decimal("0.30"),
        shipment_confidence_low=True,
        freshness_status="stale",
    )


def seed_product_process_dependency(
    db: Session,
    ctx: PilotContext,
    *,
    substitution_factor: Decimal,
) -> None:
    line = ProductionLine(
        tenant_id=ctx.tenant.id,
        plant_id=ctx.plant.id,
        code="BF-1",
        name="Blast Furnace 1",
        is_active=True,
    )
    db.add(line)
    db.flush()
    db.add(
        MaterialProcessDependency(
            tenant_id=ctx.tenant.id,
            material_id=ctx.material.id,
            process_id=line.id,
            dependency_ratio=Decimal("0.90"),
            substitution_factor=substitution_factor,
            survivability_hours=Decimal("4"),
            is_active=True,
        )
    )
    db.add_all(
        [
            ProcessProductDependency(
                tenant_id=ctx.tenant.id,
                process_id=line.id,
                product_name="HRC Coil",
                output_share_ratio=Decimal("0.60"),
                product_value_per_mt=Decimal("76000"),
                operational_criticality_factor=Decimal("1.25"),
                is_active=True,
            ),
            ProcessProductDependency(
                tenant_id=ctx.tenant.id,
                process_id=line.id,
                product_name="Billets",
                output_share_ratio=Decimal("0.40"),
                product_value_per_mt=Decimal("62000"),
                operational_criticality_factor=Decimal("1.00"),
                is_active=True,
            ),
        ]
    )


def seed_weak_supplier_history(db: Session, ctx: PilotContext) -> None:
    for index in range(3):
        db.add(
            Shipment(
                tenant_id=ctx.tenant.id,
                shipment_id=f"WEAK-SUPPLIER-{index}",
                plant_id=ctx.plant.id,
                material_id=ctx.material.id,
                supplier_id=ctx.supplier.id,
                supplier_name=ctx.supplier.name,
                quantity_mt=Decimal("100"),
                planned_eta=NOW + timedelta(days=index + 1),
                current_eta=NOW + timedelta(days=index + 3),
                current_state=ShipmentState.INLAND_TRANSIT,
                current_milestone="truck delayed exception",
                source_of_truth="manual_upload",
                latest_update_at=NOW - timedelta(hours=24),
                last_tracking_update_at=NOW - timedelta(hours=24),
            )
        )
    db.flush()


def assert_no_procurement_actions(actions) -> None:
    text = " ".join(
        " ".join(
            [
                action.action_type,
                action.operational_reason,
                *action.supporting_signals,
                *action.reason_chain,
            ]
        ).lower()
        for action in actions
    )
    for term in FORBIDDEN_ACTION_TERMS:
        assert term not in text
