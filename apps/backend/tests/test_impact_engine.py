from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    Material,
    Plant,
    ProductionInterruptionImpactConfig,
    ProductionLine,
    Tenant,
)
from app.modules.impact.engine import calculate_impact, determine_urgency_band
from app.modules.impact.production_interruption import (
    ProductionInterruptionInputs,
    calculate_production_interruption_impact,
    get_active_interruption_config,
)


def test_urgency_band_mapping() -> None:
    assert determine_urgency_band("safe", Decimal("10"), Decimal("240")) == "monitor"
    assert determine_urgency_band("critical", Decimal("0.50"), Decimal("12")) == "immediate"
    assert determine_urgency_band("warning", Decimal("0.90"), Decimal("21.60")) == "immediate"
    assert determine_urgency_band("warning", Decimal("1.50"), Decimal("36")) == "next_72h"


def test_value_at_risk_calculation() -> None:
    impact = calculate_impact(
        plant_code="P1",
        material_code="COKING_COAL",
        days_of_cover=Decimal("3.00"),
        status="critical",
        threshold_days=Decimal("5.00"),
        warning_days=Decimal("8.00"),
        daily_consumption_mt=Decimal("100.00"),
        effective_inbound_pipeline_mt=Decimal("250.00"),
        confidence_level="high",
    )
    assert impact.estimated_production_exposure_mt == Decimal("260.00")
    assert impact.estimated_value_at_risk == Decimal("83200.00")
    assert impact.value_per_mt_used == Decimal("320.00")
    assert impact.criticality_multiplier_used == Decimal("1.30")


def test_production_exposure_calculation_for_warning() -> None:
    impact = calculate_impact(
        plant_code="P2",
        material_code="LIMESTONE",
        days_of_cover=Decimal("7.00"),
        status="warning",
        threshold_days=Decimal("5.00"),
        warning_days=Decimal("8.00"),
        daily_consumption_mt=Decimal("100.00"),
        effective_inbound_pipeline_mt=Decimal("120.00"),
        confidence_level="medium",
    )
    assert impact.estimated_production_exposure_mt == Decimal("81.00")
    assert impact.estimated_value_at_risk == Decimal("6075.00")


def test_risk_hours_and_value_at_risk_decay_with_elapsed_time() -> None:
    impact = calculate_impact(
        plant_code="P1",
        material_code="COKING_COAL",
        days_of_cover=Decimal("3.00"),
        status="critical",
        threshold_days=Decimal("5.00"),
        warning_days=Decimal("8.00"),
        daily_consumption_mt=Decimal("100.00"),
        effective_inbound_pipeline_mt=Decimal("250.00"),
        confidence_level="high",
        elapsed_hours_since_snapshot=Decimal("48.00"),
    )
    assert impact.risk_hours_remaining == Decimal("24.00")
    assert impact.estimated_production_exposure_mt == Decimal("520.00")
    assert impact.estimated_value_at_risk == Decimal("166400.00")


def test_operational_interruption_impact_calculates_with_full_config() -> None:
    result = calculate_production_interruption_impact(
        interruption_inputs(days_of_cover=Decimal("1"), risk_hours_remaining=Decimal("24")),
        interruption_config(),
    )

    assert result.calculation_status == "calculated"
    assert result.estimated_interruption_hours == Decimal("48.00")
    assert result.gross_production_impact == Decimal("2400000.00")
    assert result.downtime_impact == Decimal("240000.00")
    assert result.restart_impact == Decimal("100000.00")
    assert result.gross_operational_impact == Decimal("3014000.00")
    assert result.interruption_probability == Decimal("0.7500")
    assert result.final_estimated_impact == Decimal("2260500.00")
    assert result.operational_interruption_impact == result.final_estimated_impact


def test_operational_interruption_impact_requires_config() -> None:
    result = calculate_production_interruption_impact(
        interruption_inputs(),
        None,
    )

    assert result.calculation_status == "insufficient_config"
    assert result.material_exposure_value == Decimal("83200.00")
    assert result.operational_interruption_impact is None
    assert "production_rate_mt_per_hour" in result.missing_config_fields


def test_substitution_factor_reduces_interruption_hours() -> None:
    base = calculate_production_interruption_impact(
        interruption_inputs(risk_hours_remaining=Decimal("24")),
        interruption_config(substitution_factor=Decimal("0")),
    )
    substituted = calculate_production_interruption_impact(
        interruption_inputs(risk_hours_remaining=Decimal("24")),
        interruption_config(substitution_factor=Decimal("0.50")),
    )

    assert substituted.estimated_interruption_hours == base.estimated_interruption_hours / 2


def test_line_dependency_ratio_reduces_interruption_hours() -> None:
    result = calculate_production_interruption_impact(
        interruption_inputs(risk_hours_remaining=Decimal("24")),
        interruption_config(line_dependency_ratio=Decimal("0.25")),
    )

    assert result.estimated_interruption_hours == Decimal("12.00")


def test_zero_interruption_hours_has_zero_restart_impact() -> None:
    result = calculate_production_interruption_impact(
        interruption_inputs(risk_hours_remaining=Decimal("120")),
        interruption_config(
            restart_time_hours=Decimal("4"), survivable_hours_without_material=Decimal("8")
        ),
    )

    assert result.estimated_interruption_hours == Decimal("0.00")
    assert result.restart_impact == Decimal("0.00")
    assert result.final_estimated_impact == Decimal("0.00")


def test_probability_override_is_respected() -> None:
    result = calculate_production_interruption_impact(
        interruption_inputs(risk_hours_remaining=Decimal("24")),
        interruption_config(interruption_probability_override=Decimal("0.33")),
    )

    assert result.interruption_probability == Decimal("0.3300")


def test_probability_is_clamped() -> None:
    result = calculate_production_interruption_impact(
        interruption_inputs(
            risk_hours_remaining=Decimal("1"),
            trusted_inbound_ratio=Decimal("0.10"),
            shipment_confidence_low=True,
            freshness_status="critical",
        ),
        interruption_config(substitution_factor=Decimal("0")),
    )

    assert result.interruption_probability == Decimal("0.9500")


def test_missing_days_of_cover_and_risk_hours_returns_insufficient_data() -> None:
    result = calculate_production_interruption_impact(
        interruption_inputs(days_of_cover=None, risk_hours_remaining=None),
        interruption_config(),
    )

    assert result.calculation_status == "insufficient_data"
    assert result.operational_interruption_impact is None


def test_interruption_config_lookup_preserves_tenant_isolation() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            tenant_a, plant_a, material_a = seed_context(db, "Tenant A", "tenant-a")
            tenant_b, plant_b, material_b = seed_context(db, "Tenant B", "tenant-b")
            db.add(
                interruption_config(
                    tenant_id=tenant_b.id,
                    plant_id=plant_b.id,
                    material_id=material_b.id,
                    finished_goods_value_per_mt=Decimal("9999"),
                )
            )
            db.commit()

            assert (
                get_active_interruption_config(
                    db,
                    tenant_id=tenant_a.id,
                    plant_id=plant_a.id,
                    material_id=material_a.id,
                )
                is None
            )
            config_b = get_active_interruption_config(
                db,
                tenant_id=tenant_b.id,
                plant_id=plant_b.id,
                material_id=material_b.id,
            )
            assert config_b is not None
            assert config_b.finished_goods_value_per_mt == Decimal("9999.00")
    finally:
        Base.metadata.drop_all(bind=engine)


def test_interruption_config_lookup_prefers_exact_production_line_match() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            tenant, plant, material = seed_context(db, "Tenant A", "tenant-a")
            line = ProductionLine(
                tenant_id=tenant.id,
                plant_id=plant.id,
                code="BF1",
                name="Blast Furnace 1",
                is_active=True,
            )
            db.add(line)
            db.flush()
            default_config = interruption_config(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                production_line_id=None,
                finished_goods_value_per_mt=Decimal("1000"),
            )
            line_config = interruption_config(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                production_line_id=line.id,
                finished_goods_value_per_mt=Decimal("2000"),
            )
            db.add_all([default_config, line_config])
            db.commit()

            matched = get_active_interruption_config(
                db,
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                production_line_id=line.id,
            )

            assert matched is not None
            assert matched.production_line_id == line.id
            assert matched.finished_goods_value_per_mt == Decimal("2000.00")
    finally:
        Base.metadata.drop_all(bind=engine)


def test_interruption_config_lookup_falls_back_to_unlined_plant_material_config() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            tenant, plant, material = seed_context(db, "Tenant A", "tenant-a")
            line = ProductionLine(
                tenant_id=tenant.id,
                plant_id=plant.id,
                code="BF1",
                name="Blast Furnace 1",
                is_active=True,
            )
            other_line = ProductionLine(
                tenant_id=tenant.id,
                plant_id=plant.id,
                code="BF2",
                name="Blast Furnace 2",
                is_active=True,
            )
            db.add_all([line, other_line])
            db.flush()
            default_config = interruption_config(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                production_line_id=None,
                finished_goods_value_per_mt=Decimal("1000"),
            )
            other_line_config = interruption_config(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                production_line_id=other_line.id,
                finished_goods_value_per_mt=Decimal("2000"),
            )
            db.add_all([default_config, other_line_config])
            db.commit()

            matched = get_active_interruption_config(
                db,
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                production_line_id=line.id,
            )

            assert matched is not None
            assert matched.production_line_id is None
            assert matched.finished_goods_value_per_mt == Decimal("1000.00")
    finally:
        Base.metadata.drop_all(bind=engine)


def interruption_inputs(**overrides) -> ProductionInterruptionInputs:
    values = {
        "tenant_id": 1,
        "plant_id": 1,
        "material_id": 1,
        "material_exposure_value": Decimal("83200"),
        "days_of_cover": Decimal("1"),
        "risk_hours_remaining": Decimal("24"),
        "urgency_band": "next_24h",
        "continuity_severity": "critical",
        "projected_exhaustion_date": None,
        "next_trusted_inbound_eta": None,
        "trusted_inbound_ratio": Decimal("0.80"),
        "shipment_confidence_low": False,
        "freshness_status": "fresh",
    }
    values.update(overrides)
    return ProductionInterruptionInputs(**values)


def interruption_config(**overrides) -> ProductionInterruptionImpactConfig:
    values = {
        "tenant_id": 1,
        "plant_id": 1,
        "material_id": 1,
        "production_line_id": None,
        "production_rate_mt_per_hour": Decimal("50"),
        "finished_goods_value_per_mt": Decimal("1000"),
        "survivable_hours_without_material": Decimal("8"),
        "line_dependency_ratio": Decimal("1"),
        "downtime_cost_per_hour": Decimal("5000"),
        "restart_cost": Decimal("100000"),
        "restart_time_hours": Decimal("12"),
        "substitution_factor": Decimal("0"),
        "cascading_impact_factor": Decimal("1.10"),
        "interruption_probability_override": None,
        "currency": "INR",
        "is_active": True,
    }
    values.update(overrides)
    return ProductionInterruptionImpactConfig(**values)


def seed_context(db: Session, name: str, slug: str) -> tuple[Tenant, Plant, Material]:
    tenant = Tenant(name=name, slug=slug)
    db.add(tenant)
    db.flush()
    plant = Plant(tenant_id=tenant.id, code="P1", name="Plant 1", location="India")
    material = Material(
        tenant_id=tenant.id,
        code="M1",
        name="Material 1",
        category="raw",
        uom="MT",
    )
    db.add_all([plant, material])
    db.flush()
    return tenant, plant, material
