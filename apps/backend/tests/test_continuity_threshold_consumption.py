from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.rules.engine import evaluate_inventory_rules
from app.modules.stock.schemas import InventoryContinuityResult

NOW = datetime(2026, 5, 19, 8, tzinfo=UTC)


def test_custom_warning_days_changes_warning_classification() -> None:
    risks = evaluate_inventory_rules(
        inventory(days_of_cover=Decimal("20"), warning_days=Decimal("30")),
        now=NOW,
    )

    breach = risk_by_type(risks, "days_of_cover_breach")
    assert breach.severity == "medium"
    assert "configured warning threshold" in " ".join(breach.rule_reasons)


def test_healthy_material_above_warning_days_does_not_emit_cover_breach() -> None:
    risks = evaluate_inventory_rules(
        inventory(days_of_cover=Decimal("20"), warning_days=Decimal("8")),
        now=NOW,
    )

    assert risk_by_type(risks, "days_of_cover_breach") is None
    assert risk_by_type(risks, "protected_reserve_breach") is None


def test_custom_threshold_days_changes_critical_classification() -> None:
    risks = evaluate_inventory_rules(
        inventory(days_of_cover=Decimal("10"), threshold_days=Decimal("15")),
        now=NOW,
    )

    breach = risk_by_type(risks, "days_of_cover_breach")
    assert breach.severity == "critical"
    assert "configured critical threshold" in " ".join(breach.rule_reasons)


def test_custom_stockout_alert_horizon_changes_projected_stockout_trigger() -> None:
    default_risks = evaluate_inventory_rules(
        inventory(days_of_cover=Decimal("20"), projected_in_days=Decimal("3")),
        now=NOW,
    )
    configured_risks = evaluate_inventory_rules(
        inventory(
            days_of_cover=Decimal("20"),
            projected_in_days=Decimal("3"),
            stockout_alert_horizon_days=Decimal("7"),
        ),
        now=NOW,
    )

    assert risk_by_type(default_risks, "projected_stockout") is None
    stockout = risk_by_type(configured_risks, "projected_stockout")
    assert stockout is not None
    reasons = " ".join(stockout.rule_reasons)
    assert "7.00 days" in reasons
    assert "configured projected stockout alert horizon" in reasons


def test_minimum_buffer_stock_days_elevates_protected_reserve_risk() -> None:
    risks = evaluate_inventory_rules(
        inventory(days_of_cover=Decimal("12"), minimum_buffer_stock_days=Decimal("15")),
        now=NOW,
    )

    assert risk_by_type(risks, "days_of_cover_breach") is None
    breach = risk_by_type(risks, "protected_reserve_breach")
    assert breach.severity == "medium"
    assert "Protected reserve days threshold was breached" in " ".join(breach.rule_reasons)


def test_minimum_buffer_stock_mt_elevates_protected_reserve_risk() -> None:
    risks = evaluate_inventory_rules(
        inventory(
            days_of_cover=Decimal("20"),
            usable_quantity=Decimal("90"),
            minimum_buffer_stock_mt=Decimal("100"),
        ),
        now=NOW,
    )

    assert risk_by_type(risks, "days_of_cover_breach") is None
    breach = risk_by_type(risks, "protected_reserve_breach")
    assert breach.severity == "medium"
    assert "Protected reserve quantity threshold was breached" in " ".join(breach.rule_reasons)


def test_missing_config_uses_existing_fallback_defaults() -> None:
    risks = evaluate_inventory_rules(
        inventory(
            days_of_cover=Decimal("4"),
            projected_in_days=Decimal("3"),
            threshold_days=None,
            warning_days=None,
        ),
        now=NOW,
    )

    breach = risk_by_type(risks, "days_of_cover_breach")
    assert breach.severity == "high"
    assert "default thresholds" in " ".join(breach.rule_reasons)
    assert risk_by_type(risks, "projected_stockout") is None


def inventory(
    *,
    days_of_cover: Decimal,
    usable_quantity: Decimal = Decimal("200"),
    threshold_days: Decimal | None = Decimal("5"),
    warning_days: Decimal | None = Decimal("8"),
    minimum_buffer_stock_days: Decimal | None = None,
    minimum_buffer_stock_mt: Decimal | None = None,
    stockout_alert_horizon_days: Decimal | None = None,
    projected_in_days: Decimal | None = None,
) -> InventoryContinuityResult:
    projected = (
        NOW + timedelta(days=float(projected_in_days)) if projected_in_days is not None else None
    )
    return InventoryContinuityResult(
        plant_reference="P1",
        material_reference="M1",
        on_hand_quantity=usable_quantity,
        reserved_quantity=Decimal("0"),
        blocked_quantity=Decimal("0"),
        quality_hold_quantity=Decimal("0"),
        usable_quantity=usable_quantity,
        inbound_committed_quantity=Decimal("0"),
        inbound_uncertain_quantity=Decimal("0"),
        daily_consumption_rate=Decimal("10"),
        days_of_cover=days_of_cover,
        raw_days_of_cover=days_of_cover,
        threshold_days=threshold_days,
        warning_days=warning_days,
        minimum_buffer_stock_days=minimum_buffer_stock_days,
        minimum_buffer_stock_mt=minimum_buffer_stock_mt,
        stockout_alert_horizon_days=stockout_alert_horizon_days,
        projected_exhaustion_date=projected,
        unit="MT",
        calculation_reasons=[],
    )


def risk_by_type(risks, risk_type: str):
    return next((risk for risk in risks if risk.risk_type == risk_type), None)
