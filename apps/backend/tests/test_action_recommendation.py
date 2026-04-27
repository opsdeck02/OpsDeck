from decimal import Decimal

from app.modules.recommendations.engine import (
    RecommendationSignal,
    action_deadline_hours_for,
    recommend_action,
)


def test_critical_risk_recommendation_mapping() -> None:
    action = recommend_action(
        status="critical",
        urgency_band="next_72h",
        confidence_level="medium",
        raw_inbound_pipeline_mt=Decimal("500"),
        effective_inbound_pipeline_mt=Decimal("200"),
        inbound_protection_indicator="reduced",
        shipment_signals=[],
    )
    assert action.recommended_action_code == "validate_stock_and_expedite_inbound"
    assert action.owner_role_recommended == "planner_user"


def test_low_confidence_recommendation_mapping() -> None:
    action = recommend_action(
        status="critical",
        urgency_band="immediate",
        confidence_level="low",
        raw_inbound_pipeline_mt=Decimal("200"),
        effective_inbound_pipeline_mt=Decimal("80"),
        inbound_protection_indicator="weak",
        shipment_signals=[
            RecommendationSignal(
                shipment_state="at_port",
                freshness_label="stale",
                confidence="low",
            )
        ],
    )
    assert action.recommended_action_code == "validate_eta_now"
    assert action.owner_role_recommended == "logistics_user"


def test_deadline_mapping() -> None:
    assert action_deadline_hours_for("immediate") == 4
    assert action_deadline_hours_for("next_24h") == 12
    assert action_deadline_hours_for("next_72h") == 24
    assert action_deadline_hours_for("monitor") == 48
