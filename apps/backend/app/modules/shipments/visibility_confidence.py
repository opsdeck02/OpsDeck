from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models import Shipment, ShipmentInboundTrustConfig
from app.models.enums import ShipmentState

PROFILE_CADENCE_HOURS = {
    "ocean": Decimal("72"),
    "port": Decimal("24"),
    "inland": Decimal("6"),
    "rail": Decimal("24"),
    "mixed": Decimal("24"),
    "unknown": Decimal("24"),
}

PROFILE_BASE_CONFIDENCE = {
    "ocean": Decimal("0.90"),
    "port": Decimal("0.80"),
    "inland": Decimal("0.75"),
    "rail": Decimal("0.80"),
    "mixed": Decimal("0.75"),
    "unknown": Decimal("0.60"),
}

ETA_TOLERANCE_PROFILE_BY_VISIBILITY = {
    "ocean": "tolerant",
    "port": "moderate",
    "rail": "moderate",
    "inland": "strict",
    "mixed": "moderate",
    "unknown": "moderate",
}

ETA_DRIFT_TOLERANCE_HOURS = {
    "tolerant": Decimal("24"),
    "moderate": Decimal("12"),
    "strict": Decimal("4"),
    "very_strict": Decimal("2"),
}

ETA_BEHAVIOR_CONFIDENCE_EFFECT = {
    "stable": Decimal("0"),
    "drifting": Decimal("-0.10"),
    "repeatedly_drifting": Decimal("-0.20"),
    "volatile": Decimal("-0.35"),
    "recovering": Decimal("0.05"),
    "degraded": Decimal("-0.25"),
    "unknown": Decimal("-0.10"),
}

ABNORMAL_STATES = {
    ShipmentState.DELAYED,
    ShipmentState.CANCELLED,
}
ABNORMAL_KEYWORDS = {"delayed", "cancelled", "blocked", "hold", "exception"}
INBOUND_EXCLUDED_STATES = {ShipmentState.DELIVERED, ShipmentState.CANCELLED}
NEAR_DESTINATION_KEYWORDS = {
    "arriving",
    "final_delivery",
    "final delivery",
    "unloading",
    "near_plant",
    "near plant",
    "gate_in",
    "gate in",
}
REPEATED_DRIFT_DELAY_STATUSES = {"watch", "delayed", "degraded"}


class EtaBehaviorResult(BaseModel):
    eta_behavior_status: str
    eta_context_tolerance_profile: str
    eta_confidence_penalty: Decimal
    eta_drift_hours: Decimal | None
    eta_drift_tolerance_hours: Decimal
    eta_reason_chain: list[str]


class VisibilityConfidenceResult(BaseModel):
    visibility_profile: str
    expected_visibility_cadence_hours: Decimal
    hours_since_update: Decimal | None
    eta_stability_status: str
    eta_behavior_status: str = "unknown"
    eta_context_tolerance_profile: str = "moderate"
    eta_confidence_penalty: Decimal = Decimal("0.00")
    eta_drift_tolerance_hours: Decimal | None = None
    abnormal_visibility_behavior: bool
    visibility_confidence: Decimal
    trusted_inbound_protection_ratio: Decimal
    physical_inbound_quantity_mt: Decimal
    trusted_inbound_protection_mt: Decimal
    visibility_uncertain_quantity_mt: Decimal
    reason_chain: list[str]


def calculate_visibility_confidence(
    shipment: Shipment,
    *,
    now: datetime | None = None,
    trust_config: ShipmentInboundTrustConfig | None = None,
) -> VisibilityConfidenceResult:
    evaluated_at = ensure_utc(now or datetime.now(UTC))
    physical_quantity = shipment.quantity_mt
    profile = trust_config.visibility_profile if trust_config is not None else infer_visibility_profile(shipment)
    cadence = (
        trust_config.expected_visibility_cadence_hours
        if trust_config is not None
        else PROFILE_CADENCE_HOURS[profile]
    )
    confidence = PROFILE_BASE_CONFIDENCE[profile]
    reasons = [
        (
            f"Configured visibility profile used as {profile}."
            if trust_config is not None
            else f"Visibility profile inferred as {profile}."
        ),
        f"Expected visibility cadence is {cadence} hours.",
        f"Physical inbound quantity is {physical_quantity} MT.",
    ]

    tracked_at = (
        shipment.last_tracking_update_at or shipment.latest_update_at or shipment.updated_at
    )
    hours_since_update = None
    if tracked_at is None:
        reasons.append("No shipment update timestamp was available.")
    else:
        delta = evaluated_at - ensure_utc(tracked_at)
        hours_since_update = quantize_decimal(Decimal(str(delta.total_seconds())) / Decimal("3600"))
        reasons.append(f"Hours since last visibility update is {hours_since_update}.")

    abnormal = abnormal_visibility_behavior(shipment)
    eta_behavior = calculate_eta_behavior(
        shipment,
        visibility_profile=profile,
        hours_since_update=hours_since_update,
        expected_visibility_cadence_hours=cadence,
        abnormal_visibility=abnormal,
        eta_drift_tolerance_hours=(
            trust_config.eta_drift_tolerance_hours if trust_config is not None else None
        ),
    )
    eta_status = eta_stability_status_from_behavior(eta_behavior.eta_behavior_status)
    reasons.extend(eta_behavior.eta_reason_chain)
    reasons.append(f"ETA stability status is {eta_status}.")

    if hours_since_update is not None:
        if hours_since_update <= cadence:
            reasons.append("Update age is within expected cadence; no age penalty applied.")
        elif hours_since_update <= cadence * Decimal("2"):
            penalty = (
                Decimal("0.05")
                if profile == "ocean" and eta_status == "stable"
                else Decimal("0.15")
            )
            confidence -= penalty
            reasons.append(
                f"Update age exceeded expected cadence; applied {penalty} confidence penalty."
            )
        else:
            penalty = (
                Decimal("0.15")
                if profile == "ocean" and eta_status == "stable"
                else Decimal("0.35")
            )
            confidence -= penalty
            reasons.append(
                "Update age exceeded twice the expected cadence; "
                f"applied {penalty} confidence penalty."
            )

    confidence += eta_behavior.eta_confidence_penalty
    if eta_behavior.eta_confidence_penalty < 0:
        reasons.append(
            f"ETA {eta_behavior.eta_behavior_status} applied "
            f"{abs(eta_behavior.eta_confidence_penalty)} confidence penalty."
        )
    elif eta_behavior.eta_confidence_penalty > 0:
        reasons.append(
            "Confidence partially restored because ETA stabilized and abnormal "
            "shipment conditions cleared."
        )

    if abnormal:
        confidence -= Decimal("0.30")
        reasons.append("Abnormal shipment state or milestone applied 0.30 confidence penalty.")

    if shipment.current_eta is None and tracked_at is None:
        confidence -= Decimal("0.20")
        reasons.append("Missing ETA and update timestamp applied 0.20 confidence penalty.")

    if trust_config is not None and not trust_config.allow_unverified_inbound_protection:
        unverified = shipment.current_eta is None or tracked_at is None
        if unverified and confidence > trust_config.weak_visibility_threshold:
            confidence = trust_config.weak_visibility_threshold
            reasons.append(
                "Configured unverified inbound handling capped trusted protection at "
                f"weak visibility threshold {trust_config.weak_visibility_threshold}; "
                "physical inbound quantity remains unchanged."
            )

    confidence = clamp(confidence)
    trusted_quantity = quantize_decimal(physical_quantity * confidence)
    uncertain_quantity = quantize_decimal(physical_quantity - trusted_quantity)
    reasons.append(f"Visibility confidence is {confidence}.")
    reasons.append(
        f"Trusted inbound protection is {trusted_quantity} MT; "
        f"visibility uncertainty is {uncertain_quantity} MT."
    )

    return VisibilityConfidenceResult(
        visibility_profile=profile,
        expected_visibility_cadence_hours=cadence,
        hours_since_update=hours_since_update,
        eta_stability_status=eta_status,
        eta_behavior_status=eta_behavior.eta_behavior_status,
        eta_context_tolerance_profile=eta_behavior.eta_context_tolerance_profile,
        eta_confidence_penalty=eta_behavior.eta_confidence_penalty,
        eta_drift_tolerance_hours=eta_behavior.eta_drift_tolerance_hours,
        abnormal_visibility_behavior=abnormal,
        visibility_confidence=confidence,
        trusted_inbound_protection_ratio=confidence,
        physical_inbound_quantity_mt=quantize_decimal(physical_quantity),
        trusted_inbound_protection_mt=trusted_quantity,
        visibility_uncertain_quantity_mt=uncertain_quantity,
        reason_chain=reasons,
    )


def infer_visibility_profile(shipment: Shipment) -> str:
    state = state_value(shipment)
    milestone = (shipment.current_milestone or "").lower()
    source = (shipment.source_of_truth or "").lower()
    if shipment.vessel_name or shipment.imo_number or shipment.mmsi:
        return "ocean"
    if state in {"at_port", "discharging"} or any(
        token in milestone for token in ("port", "discharg", "berth")
    ):
        return "port"
    if state == "inland_transit" or any(
        token in milestone for token in ("inland", "truck", "trucked", "dispatch", "en_route")
    ):
        return "inland"
    if "rail" in milestone or "rail" in source:
        return "rail"
    return "unknown"


def calculate_eta_behavior(
    shipment: Shipment,
    *,
    visibility_profile: str,
    hours_since_update: Decimal | None,
    expected_visibility_cadence_hours: Decimal,
    abnormal_visibility: bool,
    eta_drift_tolerance_hours: Decimal | None = None,
) -> EtaBehaviorResult:
    tolerance_profile = eta_context_tolerance_profile(shipment, visibility_profile)
    tolerance_hours = eta_drift_tolerance_hours or ETA_DRIFT_TOLERANCE_HOURS[tolerance_profile]
    current_eta = shipment.current_eta
    planned_eta = shipment.planned_eta
    latest_eta = shipment.latest_eta
    reasons = [
        (
            f"Shipment classified as {visibility_profile} profile with "
            f"{tolerance_profile} ETA expectations."
        ),
        (
            f"Configured ETA drift tolerance is {tolerance_hours} hours."
            if eta_drift_tolerance_hours is not None
            else f"ETA drift tolerance is {tolerance_hours} hours."
        ),
    ]
    if current_eta is None or planned_eta is None:
        reasons.append("ETA behavior is unknown because current or planned ETA is missing.")
        return EtaBehaviorResult(
            eta_behavior_status="unknown",
            eta_context_tolerance_profile=tolerance_profile,
            eta_confidence_penalty=ETA_BEHAVIOR_CONFIDENCE_EFFECT["unknown"],
            eta_drift_hours=None,
            eta_drift_tolerance_hours=tolerance_hours,
            eta_reason_chain=reasons,
        )

    drift_hours = eta_slip_hours(current_eta, planned_eta)
    previous_drift_hours = (
        eta_slip_hours(latest_eta, planned_eta) if latest_eta is not None else None
    )
    reasons.append(f"ETA drift is {drift_hours} hours.")

    delay_status = (shipment.delay_status or "").lower()
    stale_beyond_double_cadence = (
        hours_since_update is not None
        and hours_since_update > expected_visibility_cadence_hours * Decimal("2")
    )

    if (
        previous_drift_hours is not None
        and previous_drift_hours > tolerance_hours
        and ensure_utc(current_eta) <= ensure_utc(latest_eta)
        and not abnormal_visibility
    ):
        status = "recovering"
        reasons.append(
            "ETA was previously beyond tolerance but current ETA has stabilized or improved."
        )
    elif (
        drift_hours > tolerance_hours
        and drift_hours > tolerance_hours * Decimal("2")
        and stale_beyond_double_cadence
        and abnormal_visibility
    ):
        status = "volatile"
        reasons.append(
            "ETA volatility detected because degraded drift, stale visibility, and abnormal "
            "shipment behavior are present together."
        )
    elif repeated_eta_drift(
        drift_hours=drift_hours,
        previous_drift_hours=previous_drift_hours,
        tolerance_hours=tolerance_hours,
        delay_status=delay_status,
        stale_beyond_double_cadence=stale_beyond_double_cadence,
    ):
        status = "repeatedly_drifting"
        reasons.append(f"ETA repeatedly drifting beyond {tolerance_profile} tolerance profile.")
    elif drift_hours <= tolerance_hours:
        status = "stable"
        reasons.append(
            f"ETA drift of {drift_hours} hours remains within {tolerance_profile} tolerance."
        )
    elif drift_hours <= tolerance_hours * Decimal("2"):
        status = "drifting"
        reasons.append(f"ETA drift exceeds {tolerance_profile} tolerance once.")
    else:
        status = "degraded"
        reasons.append(f"ETA drift is materially beyond {tolerance_profile} tolerance.")

    return EtaBehaviorResult(
        eta_behavior_status=status,
        eta_context_tolerance_profile=tolerance_profile,
        eta_confidence_penalty=ETA_BEHAVIOR_CONFIDENCE_EFFECT[status],
        eta_drift_hours=quantize_decimal(drift_hours),
        eta_drift_tolerance_hours=tolerance_hours,
        eta_reason_chain=reasons,
    )


def eta_context_tolerance_profile(shipment: Shipment, visibility_profile: str) -> str:
    if near_destination(shipment):
        return "very_strict"
    return ETA_TOLERANCE_PROFILE_BY_VISIBILITY.get(visibility_profile, "moderate")


def near_destination(shipment: Shipment) -> bool:
    state_text = state_value(shipment)
    milestone = (shipment.current_milestone or "").lower()
    haystack = " ".join([state_text, milestone])
    return any(keyword in haystack for keyword in NEAR_DESTINATION_KEYWORDS)


def eta_slip_hours(current_eta: datetime, baseline_eta: datetime) -> Decimal:
    delta = ensure_utc(current_eta) - ensure_utc(baseline_eta)
    slip_hours = Decimal(str(delta.total_seconds())) / Decimal("3600")
    return max(Decimal("0"), quantize_decimal(slip_hours))


def repeated_eta_drift(
    *,
    drift_hours: Decimal,
    previous_drift_hours: Decimal | None,
    tolerance_hours: Decimal,
    delay_status: str,
    stale_beyond_double_cadence: bool,
) -> bool:
    if drift_hours <= tolerance_hours:
        return False
    if (
        previous_drift_hours is not None
        and previous_drift_hours > Decimal("0")
        and drift_hours > previous_drift_hours
        and delay_status in REPEATED_DRIFT_DELAY_STATUSES
    ):
        return True
    return delay_status in REPEATED_DRIFT_DELAY_STATUSES and stale_beyond_double_cadence


def eta_stability_status_from_behavior(eta_behavior_status: str) -> str:
    if eta_behavior_status in {"stable", "recovering"}:
        return "stable"
    if eta_behavior_status in {"drifting", "repeatedly_drifting"}:
        return "drifting"
    if eta_behavior_status in {"volatile", "degraded"}:
        return "degraded"
    return "unknown"


def eta_stability_status(shipment: Shipment) -> str:
    profile = infer_visibility_profile(shipment)
    behavior = calculate_eta_behavior(
        shipment,
        visibility_profile=profile,
        hours_since_update=None,
        expected_visibility_cadence_hours=PROFILE_CADENCE_HOURS[profile],
        abnormal_visibility=abnormal_visibility_behavior(shipment),
    )
    return eta_stability_status_from_behavior(behavior.eta_behavior_status)


def eta_behavior_status(shipment: Shipment) -> str:
    profile = infer_visibility_profile(shipment)
    behavior = calculate_eta_behavior(
        shipment,
        visibility_profile=profile,
        hours_since_update=None,
        expected_visibility_cadence_hours=PROFILE_CADENCE_HOURS[profile],
        abnormal_visibility=abnormal_visibility_behavior(shipment),
    )
    return behavior.eta_behavior_status


def eta_confidence_penalty(shipment: Shipment) -> Decimal:
    profile = infer_visibility_profile(shipment)
    behavior = calculate_eta_behavior(
        shipment,
        visibility_profile=profile,
        hours_since_update=None,
        expected_visibility_cadence_hours=PROFILE_CADENCE_HOURS[profile],
        abnormal_visibility=abnormal_visibility_behavior(shipment),
    )
    return behavior.eta_confidence_penalty


def abnormal_visibility_behavior(shipment: Shipment) -> bool:
    state = shipment.current_state
    if state in ABNORMAL_STATES:
        return True
    state_text = state_value(shipment)
    milestone = (shipment.current_milestone or "").lower()
    delay_status = (shipment.delay_status or "").lower()
    haystack = " ".join([state_text, milestone, delay_status])
    return any(keyword in haystack for keyword in ABNORMAL_KEYWORDS)


def is_physical_inbound_candidate(shipment: Shipment) -> bool:
    return shipment.current_state not in INBOUND_EXCLUDED_STATES


def state_value(shipment: Shipment) -> str:
    state = shipment.current_state
    return state.value if hasattr(state, "value") else str(state)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def clamp(value: Decimal) -> Decimal:
    return max(Decimal("0.00"), min(Decimal("1.00"), quantize_decimal(value)))
