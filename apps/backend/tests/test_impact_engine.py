from decimal import Decimal

from app.modules.impact.engine import calculate_impact, determine_urgency_band


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
