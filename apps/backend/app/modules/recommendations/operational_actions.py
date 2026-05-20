from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.modules.shipments.schemas import ShipmentContinuityResult
from app.modules.stock.schemas import InventoryContinuityResult

FORBIDDEN_TERMS = {
    "place order",
    "reorder",
    "buy material",
    "approve po",
    "replace supplier automatically",
}

SEVERITY_SCORE = {
    "critical": Decimal("35"),
    "high": Decimal("25"),
    "medium": Decimal("15"),
    "low": Decimal("5"),
}

EXPOSURE_SCORE = {
    "immediate": Decimal("25"),
    "near_term": Decimal("15"),
    "watch": Decimal("8"),
    "unknown": Decimal("4"),
    "none": Decimal("0"),
}

ETA_SCORE = {
    "volatile": Decimal("20"),
    "repeatedly_drifting": Decimal("16"),
    "degraded": Decimal("14"),
    "drifting": Decimal("8"),
    "unknown": Decimal("5"),
    "stable": Decimal("0"),
    "recovering": Decimal("0"),
}


class OperationalActionRecommendation(BaseModel):
    action_type: str
    urgency: str
    operational_reason: str
    supporting_signals: list[str]
    confidence_level: str
    requires_human_validation: bool
    action_priority_score: Decimal
    reason_chain: list[str]


def recommend_operational_actions(
    risk: Any,
    *,
    inventory: InventoryContinuityResult | None = None,
    shipment: ShipmentContinuityResult | None = None,
) -> list[OperationalActionRecommendation]:
    context = ActionContext.from_inputs(risk, inventory, shipment)
    actions: list[OperationalActionRecommendation] = []

    if context.normal_and_stable:
        actions.append(
            action(
                "monitor",
                "low",
                "Shipment visibility and cover position remain operationally acceptable.",
                ["cover_pressure:normal", f"eta_behavior:{context.eta_behavior_status}"],
                "high",
                context,
            )
        )
        return actions

    if context.physical_inbound_exists and (
        context.visibility_uncertain_quantity_mt > 0
        or context.trusted_protection_weak
        or context.eta_behavior_status in {"unknown", "drifting"}
    ):
        actions.append(
            action(
                "verify_inbound",
                urgency_from_risk(context, minimum="medium"),
                (
                    "Inbound quantity exists physically but operational visibility confidence "
                    "is reduced."
                ),
                [
                    "physical_inbound_exists",
                    f"trusted_inbound_ratio:{context.trusted_inbound_ratio}",
                ],
                confidence_from_context(context),
                context,
            )
        )

    if (
        context.eta_behavior_status in {"drifting", "repeatedly_drifting"}
        and context.supplier_reliability_band in {"strong", "acceptable", None}
        and not context.trusted_protection_weak
    ):
        actions.append(
            action(
                "validate_eta",
                urgency_from_risk(context, minimum="medium"),
                "ETA movement should be operationally validated before escalation.",
                [f"eta_behavior:{context.eta_behavior_status}", "visibility_partially_trusted"],
                "medium",
                context,
            )
        )

    if (
        context.cover_pressure in {"warning", "critical"}
        and context.eta_behavior_status in {"degraded", "volatile", "repeatedly_drifting"}
        and context.trusted_protection_weak
        and context.interruption_impact_meaningful
    ):
        actions.append(
            action(
                "expedite_inbound",
                urgency_from_risk(context, minimum="high"),
                "Inbound timing threatens continuity threshold protection.",
                [
                    f"cover_pressure:{context.cover_pressure}",
                    f"eta_behavior:{context.eta_behavior_status}",
                    "trusted_protection_weak",
                ],
                "medium",
                context,
            )
        )

    if (
        context.supplier_reliability_band == "weak"
        and context.eta_behavior_status in {"repeatedly_drifting", "volatile", "degraded"}
        and context.abnormal_state
    ):
        actions.append(
            action(
                "escalate_supplier",
                urgency_from_risk(context, minimum="high"),
                "Supplier-context reliability is weakening operational inbound confidence.",
                ["supplier_reliability:weak", f"eta_behavior:{context.eta_behavior_status}"],
                "medium",
                context,
            )
        )

    if (
        context.interruption_impact_high
        and context.survivable_hours_low
        and context.cover_pressure == "critical"
        and context.trusted_protection_weak
    ):
        actions.append(
            action(
                "review_recovery_plan",
                "critical",
                "Operational continuity recovery planning should be reviewed.",
                ["critical_cover_pressure", "low_survivability", "weak_inbound_protection"],
                "high",
                context,
            )
        )

    if context.substitution_viable and context.severity in {"critical", "high"}:
        actions.append(
            action(
                "activate_substitution",
                urgency_from_risk(context, minimum="high"),
                "Configured operational substitution flexibility may reduce continuity exposure.",
                [f"substitution_factor:{context.substitution_factor}"],
                "medium",
                context,
            )
        )

    if context.protected_reserve_breached and context.trusted_protection_weak:
        actions.append(
            action(
                "review_reserve_usage",
                urgency_from_risk(context, minimum="medium"),
                "Protected reserve threshold breached while inbound confidence is degraded.",
                ["protected_reserve_breach", "trusted_protection_weak"],
                "high",
                context,
            )
        )

    if (
        context.visibility_stale
        and context.eta_behavior_status in {"stable", "recovering"}
        and context.visibility_uncertainty_moderate
        and context.shipment_profile in {"ocean", "port"}
    ):
        actions.append(
            action(
                "validate_tracking_visibility",
                "medium",
                (
                    "Operational visibility cadence should be validated before treating inbound "
                    "as degraded."
                ),
                [f"shipment_profile:{context.shipment_profile}", "eta_stable"],
                "medium",
                context,
            )
        )

    if (
        context.shipment_profile in {"ocean", "port"}
        and context.port_or_hold_signal
        and context.cover_pressure in {"warning", "critical"}
    ):
        actions.append(
            action(
                "confirm_port_clearance",
                urgency_from_risk(context, minimum="medium"),
                "Confirm port clearance or discharge status because inbound timing matters.",
                [f"shipment_profile:{context.shipment_profile}", "port_or_hold_signal"],
                "medium",
                context,
            )
        )

    if (
        context.shipment_profile == "inland"
        and context.eta_behavior_status in {"degraded", "volatile", "repeatedly_drifting"}
        and context.visibility_stale
        and context.near_destination
    ):
        actions.append(
            action(
                "confirm_inland_movement",
                urgency_from_risk(context, minimum="high"),
                "Confirm inland movement because near-plant ETA confidence is degraded.",
                [
                    "inland_profile",
                    "near_destination",
                    f"eta_behavior:{context.eta_behavior_status}",
                ],
                "medium",
                context,
            )
        )

    if not actions:
        actions.append(
            action(
                "monitor",
                urgency_from_risk(context, minimum="low"),
                (
                    "Continue monitoring; current signals do not support escalation beyond "
                    "operational review."
                ),
                [f"risk_severity:{context.severity}"],
                confidence_from_context(context),
                context,
            )
        )

    return dedupe_actions(actions)


class ActionContext(BaseModel):
    severity: str
    exposure_level: str
    cover_pressure: str
    eta_behavior_status: str
    shipment_profile: str
    days_of_cover: Decimal | None
    trusted_inbound_ratio: Decimal
    physical_inbound_quantity_mt: Decimal
    trusted_inbound_protection_mt: Decimal
    visibility_uncertain_quantity_mt: Decimal
    visibility_confidence: Decimal | None
    supplier_reliability_band: str | None
    interruption_impact: Decimal | None
    survivable_hours: Decimal | None
    substitution_factor: Decimal | None
    abnormal_state: bool
    protected_reserve_breached: bool
    visibility_stale: bool
    near_destination: bool
    port_or_hold_signal: bool

    @classmethod
    def from_inputs(
        cls,
        risk: Any,
        inventory: InventoryContinuityResult | None,
        shipment: ShipmentContinuityResult | None,
    ) -> ActionContext:
        reasons = " ".join(getattr(risk, "rule_reasons", []) or [])
        impact = getattr(risk, "operational_interruption_impact", None)
        physical = decimal_from_reason(
            reasons,
            "Physical inbound quantity remains unchanged at ",
        )
        trusted = decimal_from_reason(reasons, "trusted inbound protection is ")
        uncertain = decimal_from_reason(reasons, "visibility uncertainty is ")
        if inventory is not None:
            physical = physical if physical is not None else inventory.physical_inbound_quantity_mt
            trusted = trusted if trusted is not None else inventory.trusted_inbound_protection_mt
            uncertain = (
                uncertain if uncertain is not None else inventory.visibility_uncertain_quantity_mt
            )
        physical = physical or Decimal("0")
        trusted = trusted or Decimal("0")
        uncertain = uncertain or Decimal("0")
        ratio = trusted / physical if physical > 0 else Decimal("0")
        eta_behavior = eta_behavior_from_reasons(reasons)
        profile = profile_from_reasons(reasons)
        supplier_band = supplier_band_from_reasons(reasons)
        visibility_confidence = decimal_from_reason(reasons, "Visibility confidence is ")
        exposure_level = exposure_from_risk(
            getattr(risk, "severity", "low"), getattr(risk, "days_of_cover", None)
        )
        return cls(
            severity=getattr(risk, "severity", "low"),
            exposure_level=exposure_level,
            cover_pressure=cover_pressure_from_inputs(risk, inventory, reasons),
            eta_behavior_status=eta_behavior,
            shipment_profile=profile,
            days_of_cover=getattr(risk, "days_of_cover", None),
            trusted_inbound_ratio=ratio,
            physical_inbound_quantity_mt=physical,
            trusted_inbound_protection_mt=trusted,
            visibility_uncertain_quantity_mt=uncertain,
            visibility_confidence=visibility_confidence,
            supplier_reliability_band=supplier_band,
            interruption_impact=(
                impact.final_estimated_impact
                if impact is not None
                and getattr(impact, "final_estimated_impact", None) is not None
                else None
            ),
            survivable_hours=decimal_from_impact_reason(
                getattr(impact, "reason_chain", []) if impact is not None else [],
                "survivable_hours_without_material=",
            ),
            substitution_factor=decimal_from_impact_reason(
                getattr(impact, "reason_chain", []) if impact is not None else [],
                "substitution_factor=",
            ),
            abnormal_state=contains_any(
                reasons, {"abnormal", "hold", "blocked", "exception", "cancelled"}
            ),
            protected_reserve_breached="Protected reserve" in reasons
            or getattr(risk, "risk_type", "") == "protected_reserve_breach",
            visibility_stale=contains_any(
                reasons, {"stale", "critical visibility", "stale visibility"}
            )
            or (
                shipment is not None and shipment.tracking_freshness_status in {"stale", "critical"}
            ),
            near_destination=contains_any(
                reasons, {"near_plant", "near plant", "gate_in", "final_delivery"}
            ),
            port_or_hold_signal=contains_any(reasons, {"port", "discharg", "berth", "hold"}),
        )

    @property
    def trusted_protection_weak(self) -> bool:
        return self.physical_inbound_quantity_mt > 0 and self.trusted_inbound_ratio < Decimal(
            "0.50"
        )

    @property
    def physical_inbound_exists(self) -> bool:
        return self.physical_inbound_quantity_mt > 0

    @property
    def normal_and_stable(self) -> bool:
        return (
            self.cover_pressure == "normal"
            and self.eta_behavior_status in {"stable", "recovering"}
            and not self.trusted_protection_weak
            and self.visibility_uncertain_quantity_mt
            <= self.physical_inbound_quantity_mt * Decimal("0.20")
        )

    @property
    def interruption_impact_meaningful(self) -> bool:
        return self.interruption_impact is None or self.interruption_impact > Decimal("0")

    @property
    def interruption_impact_high(self) -> bool:
        return self.interruption_impact is not None and self.interruption_impact >= Decimal(
            "1000000"
        )

    @property
    def survivable_hours_low(self) -> bool:
        return self.survivable_hours is None or self.survivable_hours <= Decimal("4")

    @property
    def substitution_viable(self) -> bool:
        return self.substitution_factor is not None and self.substitution_factor >= Decimal("0.50")

    @property
    def visibility_uncertainty_moderate(self) -> bool:
        if self.physical_inbound_quantity_mt <= 0:
            return False
        ratio = self.visibility_uncertain_quantity_mt / self.physical_inbound_quantity_mt
        return Decimal("0.10") <= ratio < Decimal("0.50")


def action(
    action_type: str,
    urgency: str,
    operational_reason: str,
    supporting_signals: list[str],
    confidence_level: str,
    context: ActionContext,
) -> OperationalActionRecommendation:
    reason_chain = [
        operational_reason,
        "Human validation is required; OpsDeck does not automate procurement or inventory changes.",
        "Recommendation distinguishes visibility uncertainty from actual shortage.",
    ]
    reason_chain.extend(supporting_signals)
    return OperationalActionRecommendation(
        action_type=action_type,
        urgency=urgency,
        operational_reason=assert_safe_language(operational_reason),
        supporting_signals=supporting_signals,
        confidence_level=confidence_level,
        requires_human_validation=True,
        action_priority_score=priority_score(context, urgency),
        reason_chain=[assert_safe_language(reason) for reason in reason_chain],
    )


def priority_score(context: ActionContext, urgency: str) -> Decimal:
    score = SEVERITY_SCORE.get(context.severity, Decimal("5"))
    score += EXPOSURE_SCORE.get(context.exposure_level, Decimal("0"))
    score += ETA_SCORE.get(context.eta_behavior_status, Decimal("0"))
    if context.trusted_protection_weak:
        score += Decimal("12")
    if context.interruption_impact_high:
        score += Decimal("18")
    elif context.interruption_impact is not None and context.interruption_impact > 0:
        score += Decimal("8")
    if urgency == "critical":
        score += Decimal("10")
    elif urgency == "high":
        score += Decimal("6")
    return clamp_score(score)


def urgency_from_risk(context: ActionContext, *, minimum: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    if context.severity == "critical" or context.exposure_level == "immediate":
        derived = "critical"
    elif context.severity == "high" or context.exposure_level == "near_term":
        derived = "high"
    elif context.severity == "medium":
        derived = "medium"
    else:
        derived = "low"
    return derived if order[derived] >= order[minimum] else minimum


def confidence_from_context(context: ActionContext) -> str:
    if context.visibility_confidence is not None and context.visibility_confidence < Decimal(
        "0.50"
    ):
        return "low"
    if context.supplier_reliability_band == "unknown":
        return "low"
    if context.visibility_confidence is not None and context.visibility_confidence < Decimal(
        "0.75"
    ):
        return "medium"
    return "high"


def cover_pressure_from_inputs(
    risk: Any,
    inventory: InventoryContinuityResult | None,
    reasons: str,
) -> str:
    parsed = token_after(reasons, "Cover pressure is ")
    if parsed:
        return parsed.rstrip(".")
    days = getattr(risk, "days_of_cover", None)
    threshold = inventory.threshold_days if inventory is not None else None
    warning = inventory.warning_days if inventory is not None else None
    threshold = threshold or Decimal("2")
    warning = warning or Decimal("5")
    if days is None:
        return "unknown"
    if days <= threshold:
        return "critical"
    if days <= warning:
        return "warning"
    return "normal"


def exposure_from_risk(severity: str, days_of_cover: Decimal | None) -> str:
    if severity == "critical" or (days_of_cover is not None and days_of_cover <= Decimal("2")):
        return "immediate"
    if severity == "high" or (days_of_cover is not None and days_of_cover <= Decimal("5")):
        return "near_term"
    if severity in {"medium", "low"}:
        return "watch"
    return "unknown"


def eta_behavior_from_reasons(reasons: str) -> str:
    value = token_after(reasons, "ETA behavior status is ")
    if value:
        return value.rstrip(".,")
    for status in ETA_SCORE:
        if f"eta_behavior:{status}" in reasons or f"ETA {status}" in reasons:
            return status
    return "unknown"


def profile_from_reasons(reasons: str) -> str:
    value = token_after(reasons, "Visibility profile inferred as ")
    if value:
        return value.rstrip(".,")
    value = token_after(reasons, "Shipment classified as ")
    if value:
        return value.split(" ")[0].rstrip(".,")
    for profile in ("ocean", "port", "inland", "rail", "unknown"):
        if f"shipment_profile:{profile}" in reasons:
            return profile
    return "unknown"


def supplier_band_from_reasons(reasons: str) -> str | None:
    value = token_after(reasons, "Supplier reliability band is ")
    return value.rstrip(".,") if value else None


def decimal_from_reason(reasons: str, prefix: str) -> Decimal | None:
    value = token_after(reasons, prefix)
    if not value:
        return None
    cleaned = value.replace("MT", "").rstrip(".,;")
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def decimal_from_impact_reason(reasons: list[str], key: str) -> Decimal | None:
    for reason in reasons:
        if key not in reason:
            continue
        try:
            return Decimal(reason.split(key, 1)[1].split()[0].rstrip(".,;"))
        except Exception:
            return None
    return None


def token_after(text: str, prefix: str) -> str | None:
    if prefix not in text:
        return None
    return text.split(prefix, 1)[1].split(" ", 1)[0]


def contains_any(text: str, needles: set[str]) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


def assert_safe_language(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in FORBIDDEN_TERMS):
        raise ValueError(f"Unsafe procurement automation language in recommendation: {text}")
    return text


def clamp_score(value: Decimal) -> Decimal:
    return max(Decimal("0.0"), min(Decimal("100.0"), value.quantize(Decimal("0.1"))))


def dedupe_actions(
    actions: list[OperationalActionRecommendation],
) -> list[OperationalActionRecommendation]:
    seen: set[str] = set()
    deduped: list[OperationalActionRecommendation] = []
    for item in sorted(
        actions, key=lambda action_item: action_item.action_priority_score, reverse=True
    ):
        if item.action_type in seen:
            continue
        seen.add(item.action_type)
        deduped.append(item)
    return deduped
