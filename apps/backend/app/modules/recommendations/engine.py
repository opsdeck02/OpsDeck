from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RecommendationSignal:
    shipment_state: str
    freshness_label: str
    confidence: str


@dataclass(frozen=True)
class ActionRecommendation:
    recommended_action_code: str
    recommended_action_text: str
    owner_role_recommended: str
    action_deadline_hours: int
    action_priority: str
    why: list[str]


DEADLINE_HOURS = {
    "immediate": 4,
    "next_24h": 12,
    "next_72h": 24,
    "monitor": 48,
}

PRIORITY_BY_URGENCY = {
    "immediate": "urgent",
    "next_24h": "high",
    "next_72h": "medium",
    "monitor": "low",
}


def action_deadline_hours_for(urgency_band: str) -> int:
    return DEADLINE_HOURS.get(urgency_band, 48)


def action_priority_for(urgency_band: str) -> str:
    return PRIORITY_BY_URGENCY.get(urgency_band, "low")


def recommend_action(
    *,
    status: str,
    urgency_band: str,
    confidence_level: str,
    raw_inbound_pipeline_mt: Decimal,
    effective_inbound_pipeline_mt: Decimal,
    inbound_protection_indicator: str,
    shipment_signals: list[RecommendationSignal],
) -> ActionRecommendation:
    deadline = action_deadline_hours_for(urgency_band)
    priority = action_priority_for(urgency_band)
    stale_shipments = [item for item in shipment_signals if item.freshness_label == "stale"]
    low_confidence_shipments = [item for item in shipment_signals if item.confidence == "low"]
    has_port_or_discharge = any(
        item.shipment_state in {"at_port", "discharging"} for item in shipment_signals
    )
    raw_positive = raw_inbound_pipeline_mt > Decimal("0")
    effective_ratio = (
        effective_inbound_pipeline_mt / raw_inbound_pipeline_mt
        if raw_positive
        else Decimal("0")
    )

    if confidence_level == "low" and stale_shipments:
        return ActionRecommendation(
            recommended_action_code="validate_eta_now",
            recommended_action_text="Validate shipment ETA with logistics / supplier immediately",
            owner_role_recommended="logistics_user",
            action_deadline_hours=deadline,
            action_priority=priority,
            why=[
                "Risk confidence is low.",
                "At least one contributing shipment has stale tracking data.",
            ],
        )

    if has_port_or_discharge and inbound_protection_indicator == "weak":
        return ActionRecommendation(
            recommended_action_code="prioritize_port_clearance",
            recommended_action_text="Prioritize port clearance / discharge follow-through",
            owner_role_recommended="logistics_user",
            action_deadline_hours=deadline,
            action_priority=priority,
            why=[
                "A contributing shipment is already at port or discharging.",
                "Effective inbound protection is still weak.",
            ],
        )

    if status == "critical" and raw_positive and effective_ratio < Decimal("0.65"):
        return ActionRecommendation(
            recommended_action_code="validate_stock_and_expedite_inbound",
            recommended_action_text="Validate stock position and expedite inbound recovery actions",
            owner_role_recommended="planner_user",
            action_deadline_hours=deadline,
            action_priority=priority,
            why=[
                "The combination is already below the critical threshold.",
                "Effective inbound protection is materially below the raw inbound pipeline.",
            ],
        )

    if inbound_protection_indicator != "strong":
        return ActionRecommendation(
            recommended_action_code="review_recovery_plan",
            recommended_action_text="Review alternate recovery options and demand protection plan",
            owner_role_recommended="buyer_user",
            action_deadline_hours=deadline,
            action_priority=priority,
            why=[
                "Inbound protection is not strong enough to comfortably cover risk.",
            ],
        )

    return ActionRecommendation(
        recommended_action_code="review_continuity_risk",
        recommended_action_text="Review continuity risk and confirm the operating plan",
        owner_role_recommended="tenant_admin",
        action_deadline_hours=deadline,
        action_priority=priority,
        why=[
            "A warning or critical continuity signal exists and needs coordinated follow-through.",
        ],
    )
