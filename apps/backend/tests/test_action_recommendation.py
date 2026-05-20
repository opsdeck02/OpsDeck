from decimal import Decimal
from types import SimpleNamespace

from app.modules.impact.schemas import OperationalInterruptionImpact
from app.modules.recommendations.engine import (
    RecommendationSignal,
    action_deadline_hours_for,
    recommend_action,
)
from app.modules.recommendations.operational_actions import recommend_operational_actions
from app.modules.stock.continuity import calculate_inventory_continuity


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


def test_stable_shipment_recommends_monitor_only() -> None:
    actions = recommend_operational_actions(
        risk(
            severity="low",
            reasons=[
                "Cover pressure is normal.",
                "ETA behavior status is stable, mapped to low ETA threat.",
                "Physical inbound quantity remains unchanged at 100.00 MT.",
                "trusted inbound protection is 90.00 MT and visibility uncertainty is 10.00 MT.",
                "Visibility confidence is 0.90.",
            ],
        ),
        inventory=inventory(days_of_cover=Decimal("20"), trusted_ratio=Decimal("0.90")),
    )

    assert [item.action_type for item in actions] == ["monitor"]


def test_weak_trusted_inbound_recommends_verify_inbound() -> None:
    actions = action_types(
        recommend_operational_actions(
            risk(
                severity="medium",
                reasons=[
                    "Cover pressure is normal.",
                    "ETA behavior status is stable, mapped to low ETA threat.",
                    "Physical inbound quantity remains unchanged at 100.00 MT.",
                    trust_reason("40.00", "60.00"),
                ],
            ),
            inventory=inventory(days_of_cover=Decimal("20"), trusted_ratio=Decimal("0.40")),
        )
    )

    assert "verify_inbound" in actions


def test_eta_drift_recommends_validate_eta() -> None:
    actions = action_types(
        recommend_operational_actions(
            risk(
                severity="medium",
                reasons=[
                    "Cover pressure is normal.",
                    "ETA behavior status is drifting, mapped to medium ETA threat.",
                    "Physical inbound quantity remains unchanged at 100.00 MT.",
                    trust_reason("80.00", "20.00"),
                    "Supplier reliability band is acceptable.",
                ],
            ),
            inventory=inventory(days_of_cover=Decimal("20"), trusted_ratio=Decimal("0.80")),
        )
    )

    assert "validate_eta" in actions


def test_critical_cover_degraded_eta_recommends_expedite_inbound() -> None:
    actions = action_types(
        recommend_operational_actions(
            risk(
                severity="critical",
                reasons=[
                    "Cover pressure is critical.",
                    "ETA behavior status is degraded, mapped to high ETA threat.",
                    "Physical inbound quantity remains unchanged at 100.00 MT.",
                    trust_reason("30.00", "70.00"),
                ],
                impact=impact(final=Decimal("2500000")),
            ),
            inventory=inventory(days_of_cover=Decimal("1"), trusted_ratio=Decimal("0.30")),
        )
    )

    assert "expedite_inbound" in actions


def test_weak_supplier_reliability_recommends_escalate_supplier() -> None:
    actions = action_types(
        recommend_operational_actions(
            risk(
                severity="high",
                reasons=[
                    "Cover pressure is warning.",
                    "ETA behavior status is repeatedly_drifting, mapped to high ETA threat.",
                    "Supplier reliability band is weak.",
                    "Abnormal current shipment state applied penalty.",
                    "Physical inbound quantity remains unchanged at 100.00 MT.",
                    trust_reason("45.00", "55.00"),
                ],
            ),
            inventory=inventory(days_of_cover=Decimal("4"), trusted_ratio=Decimal("0.45")),
        )
    )

    assert "escalate_supplier" in actions


def test_high_impact_low_survivability_recommends_recovery_plan() -> None:
    actions = action_types(
        recommend_operational_actions(
            risk(
                severity="critical",
                reasons=[
                    "Cover pressure is critical.",
                    "ETA behavior status is degraded, mapped to high ETA threat.",
                    "Physical inbound quantity remains unchanged at 100.00 MT.",
                    trust_reason("20.00", "80.00"),
                ],
                impact=impact(
                    final=Decimal("5000000"),
                    reason_chain=["survivable_hours_without_material=2"],
                ),
            ),
            inventory=inventory(days_of_cover=Decimal("1"), trusted_ratio=Decimal("0.20")),
        )
    )

    assert "review_recovery_plan" in actions


def test_strong_substitution_recommends_activate_substitution() -> None:
    actions = action_types(
        recommend_operational_actions(
            risk(
                severity="high",
                reasons=[
                    "Cover pressure is warning.",
                    "ETA behavior status is degraded, mapped to high ETA threat.",
                    "Physical inbound quantity remains unchanged at 100.00 MT.",
                    trust_reason("40.00", "60.00"),
                ],
                impact=impact(reason_chain=["substitution_factor=0.75"]),
            ),
            inventory=inventory(days_of_cover=Decimal("4"), trusted_ratio=Decimal("0.40")),
        )
    )

    assert "activate_substitution" in actions


def test_protected_reserve_breach_recommends_review_reserve_usage() -> None:
    actions = action_types(
        recommend_operational_actions(
            risk(
                severity="medium",
                risk_type="days_of_cover_breach",
                reasons=[
                    "Protected reserve days threshold was breached.",
                    "Cover pressure is warning.",
                    "ETA behavior status is stable, mapped to low ETA threat.",
                    "Physical inbound quantity remains unchanged at 100.00 MT.",
                    trust_reason("40.00", "60.00"),
                ],
            ),
            inventory=inventory(days_of_cover=Decimal("4"), trusted_ratio=Decimal("0.40")),
        )
    )

    assert "review_reserve_usage" in actions


def test_ocean_stale_stable_eta_recommends_validate_tracking_visibility_not_panic() -> None:
    actions = recommend_operational_actions(
        risk(
            severity="low",
            reasons=[
                "Shipment classified as ocean profile with tolerant ETA expectations.",
                "tracking freshness is stale.",
                "Cover pressure is normal.",
                "ETA behavior status is stable, mapped to low ETA threat.",
                "Physical inbound quantity remains unchanged at 100.00 MT.",
                "trusted inbound protection is 70.00 MT and visibility uncertainty is 30.00 MT.",
            ],
        ),
        inventory=inventory(days_of_cover=Decimal("20"), trusted_ratio=Decimal("0.70")),
    )

    assert "validate_tracking_visibility" in action_types(actions)
    assert "expedite_inbound" not in action_types(actions)


def test_inland_degraded_near_plant_recommends_confirm_inland_movement() -> None:
    actions = action_types(
        recommend_operational_actions(
            risk(
                severity="high",
                reasons=[
                    "Shipment classified as inland profile with very_strict ETA expectations.",
                    "near_plant gate_in milestone.",
                    "visibility is stale.",
                    "Cover pressure is warning.",
                    "ETA behavior status is degraded, mapped to high ETA threat.",
                    "Physical inbound quantity remains unchanged at 100.00 MT.",
                    trust_reason("40.00", "60.00"),
                ],
            ),
            inventory=inventory(days_of_cover=Decimal("4"), trusted_ratio=Decimal("0.40")),
        )
    )

    assert "confirm_inland_movement" in actions


def test_no_reorder_recommendation_is_generated() -> None:
    actions = recommend_operational_actions(
        risk(
            severity="critical",
            reasons=[
                "Cover pressure is critical.",
                "ETA behavior status is volatile, mapped to critical ETA threat.",
                "Physical inbound quantity remains unchanged at 100.00 MT.",
                "trusted inbound protection is 10.00 MT and visibility uncertainty is 90.00 MT.",
            ],
        ),
        inventory=inventory(days_of_cover=Decimal("1"), trusted_ratio=Decimal("0.10")),
    )

    text = " ".join(
        part
        for item in actions
        for part in [item.action_type, item.operational_reason, *item.reason_chain]
    ).lower()
    assert "reorder" not in text
    assert "buy material" not in text
    assert "approve po" not in text


def test_reason_chain_and_supporting_signals_are_populated() -> None:
    action = recommend_operational_actions(
        risk(
            severity="medium",
            reasons=[
                "Cover pressure is normal.",
                "ETA behavior status is drifting, mapped to medium ETA threat.",
                "Physical inbound quantity remains unchanged at 100.00 MT.",
                trust_reason("80.00", "20.00"),
                "Supplier reliability band is acceptable.",
            ],
        ),
        inventory=inventory(days_of_cover=Decimal("20"), trusted_ratio=Decimal("0.80")),
    )[0]

    assert action.supporting_signals
    assert action.reason_chain
    assert action.requires_human_validation is True


def test_action_priority_score_clamps() -> None:
    action = recommend_operational_actions(
        risk(
            severity="critical",
            reasons=[
                "Cover pressure is critical.",
                "ETA behavior status is volatile, mapped to critical ETA threat.",
                "Physical inbound quantity remains unchanged at 100.00 MT.",
                "trusted inbound protection is 1.00 MT and visibility uncertainty is 99.00 MT.",
            ],
            impact=impact(final=Decimal("999999999")),
        ),
        inventory=inventory(days_of_cover=Decimal("1"), trusted_ratio=Decimal("0.01")),
    )[0]

    assert action.action_priority_score == Decimal("100.0")


def inventory(days_of_cover: Decimal, trusted_ratio: Decimal):
    physical = Decimal("100")
    trusted = (physical * trusted_ratio).quantize(Decimal("0.01"))
    return calculate_inventory_continuity(
        plant_reference="P1",
        material_reference="M1",
        on_hand_quantity=days_of_cover * Decimal("10"),
        daily_consumption_rate=Decimal("10"),
        inbound_committed_quantity=physical,
        trusted_inbound_quantity=trusted,
        uncertain_inbound_quantity=physical - trusted,
        physical_inbound_quantity_mt=physical,
        trusted_inbound_protection_mt=trusted,
        visibility_uncertain_quantity_mt=physical - trusted,
        unit="MT",
    )


def risk(
    *,
    severity: str,
    reasons: list[str],
    risk_type: str = "inbound_delay_against_cover",
    impact: OperationalInterruptionImpact | None = None,
):
    return SimpleNamespace(
        risk_type=risk_type,
        severity=severity,
        days_of_cover=Decimal("1") if severity == "critical" else Decimal("4"),
        rule_reasons=reasons,
        operational_interruption_impact=impact,
    )


def impact(
    final: Decimal | None = Decimal("1"),
    reason_chain: list[str] | None = None,
) -> OperationalInterruptionImpact:
    return OperationalInterruptionImpact(
        calculation_status="calculated",
        currency="INR",
        final_estimated_impact=final,
        missing_config_fields=[],
        formula_version="test",
        reason_chain=reason_chain or [],
    )


def action_types(actions):
    return {item.action_type for item in actions}


def trust_reason(trusted: str, uncertain: str) -> str:
    return (
        f"trusted inbound protection is {trusted} MT and visibility uncertainty is {uncertain} MT."
    )
