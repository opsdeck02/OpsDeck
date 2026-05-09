from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContinuityRiskSnapshot
from app.modules.risk_snapshots.schemas import RiskEscalationComparison

SEVERITY_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

EXPOSURE_ORDER = {
    "unknown": 1,
    "watch": 2,
    "near_term": 3,
    "immediate": 4,
}

BASE_SCORES = {
    "newly_exposed": Decimal("70"),
    "worsening": Decimal("75"),
    "rapidly_worsening": Decimal("90"),
    "blind_spot_risk": Decimal("85"),
    "recovering": Decimal("35"),
    "contained": Decimal("45"),
    "unknown": Decimal("50"),
}


def classify_snapshot_escalation(
    db: Session,
    current: ContinuityRiskSnapshot,
    *,
    update_snapshot: bool = False,
) -> RiskEscalationComparison:
    previous = previous_snapshot(db, current)
    comparison = compare_snapshots(current=current, previous=previous)
    if update_snapshot:
        current.escalation_state = comparison.escalation_state
        current.escalation_score = comparison.escalation_score
        current.escalation_reason = comparison.escalation_reason
    return comparison


def previous_snapshot(
    db: Session,
    current: ContinuityRiskSnapshot,
) -> ContinuityRiskSnapshot | None:
    if db.new:
        db.flush()
    return db.scalar(
        select(ContinuityRiskSnapshot)
        .where(
            ContinuityRiskSnapshot.tenant_id == current.tenant_id,
            ContinuityRiskSnapshot.risk_fingerprint == current.risk_fingerprint,
            ContinuityRiskSnapshot.snapshot_time < current.snapshot_time,
        )
        .order_by(ContinuityRiskSnapshot.snapshot_time.desc())
        .limit(1)
    )


def compare_snapshots(
    *,
    current: ContinuityRiskSnapshot,
    previous: ContinuityRiskSnapshot | None,
) -> RiskEscalationComparison:
    doc_delta = delta(current.days_of_cover, previous.days_of_cover if previous else None)
    delay_delta = delta(
        current.shipment_delay_hours,
        previous.shipment_delay_hours if previous else None,
    )
    state, reason = escalation_state_and_reason(
        current=current,
        previous=previous,
        days_of_cover_delta=doc_delta,
        shipment_delay_delta_hours=delay_delta,
    )
    score = escalation_score(state, current)

    return RiskEscalationComparison(
        escalation_state=state,
        escalation_score=score,
        escalation_reason=reason,
        prior_days_of_cover=previous.days_of_cover if previous else None,
        current_days_of_cover=current.days_of_cover,
        days_of_cover_delta=doc_delta,
        prior_shipment_delay_hours=previous.shipment_delay_hours if previous else None,
        current_shipment_delay_hours=current.shipment_delay_hours,
        shipment_delay_delta_hours=delay_delta,
        prior_severity=previous.severity if previous else None,
        current_severity=current.severity,
        prior_exposure_level=previous.exposure_level if previous else None,
        current_exposure_level=current.exposure_level,
    )


def escalation_state_and_reason(
    *,
    current: ContinuityRiskSnapshot,
    previous: ContinuityRiskSnapshot | None,
    days_of_cover_delta: Decimal | None,
    shipment_delay_delta_hours: Decimal | None,
) -> tuple[str, str]:
    if previous is None:
        return "newly_exposed", "No previous snapshot exists for this risk context."

    rapid_reasons = rapid_worsening_reasons(
        current=current,
        previous=previous,
        days_of_cover_delta=days_of_cover_delta,
        shipment_delay_delta_hours=shipment_delay_delta_hours,
    )
    if rapid_reasons:
        return "rapidly_worsening", "; ".join(rapid_reasons)

    if is_blind_spot_risk(current):
        return (
            "blind_spot_risk",
            "High-severity risk is based on stale or critical signal freshness.",
        )

    worsening = worsening_reasons(
        current=current,
        previous=previous,
        days_of_cover_delta=days_of_cover_delta,
        shipment_delay_delta_hours=shipment_delay_delta_hours,
    )
    if worsening:
        return "worsening", "; ".join(worsening)

    recovery = recovery_reasons(
        current=current,
        previous=previous,
        days_of_cover_delta=days_of_cover_delta,
        shipment_delay_delta_hours=shipment_delay_delta_hours,
    )
    if recovery:
        return "recovering", "; ".join(recovery)

    if has_comparable_values(current, previous):
        return "contained", "Previous snapshot exists and no material movement was detected."

    return "unknown", "Previous snapshot exists but comparable continuity values are insufficient."


def rapid_worsening_reasons(
    *,
    current: ContinuityRiskSnapshot,
    previous: ContinuityRiskSnapshot,
    days_of_cover_delta: Decimal | None,
    shipment_delay_delta_hours: Decimal | None,
) -> list[str]:
    reasons: list[str] = []
    if days_of_cover_delta is not None and days_of_cover_delta <= Decimal("-1.5"):
        reasons.append("Days of cover decreased by at least 1.5 days.")
    if shipment_delay_delta_hours is not None and shipment_delay_delta_hours >= Decimal("24"):
        reasons.append("Shipment delay increased by at least 24 hours.")
    if severity_rank(current.severity) == SEVERITY_ORDER["critical"] and severity_rank(
        previous.severity
    ) < SEVERITY_ORDER["critical"]:
        reasons.append("Severity worsened to critical from a lower severity.")
    return reasons


def worsening_reasons(
    *,
    current: ContinuityRiskSnapshot,
    previous: ContinuityRiskSnapshot,
    days_of_cover_delta: Decimal | None,
    shipment_delay_delta_hours: Decimal | None,
) -> list[str]:
    reasons: list[str] = []
    if days_of_cover_delta is not None and days_of_cover_delta <= Decimal("-0.5"):
        reasons.append("Days of cover decreased by at least 0.5 days.")
    if shipment_delay_delta_hours is not None and shipment_delay_delta_hours >= Decimal("6"):
        reasons.append("Shipment delay increased by at least 6 hours.")
    if exposure_rank(current.exposure_level) > exposure_rank(previous.exposure_level):
        reasons.append("Exposure level worsened.")
    return reasons


def recovery_reasons(
    *,
    current: ContinuityRiskSnapshot,
    previous: ContinuityRiskSnapshot,
    days_of_cover_delta: Decimal | None,
    shipment_delay_delta_hours: Decimal | None,
) -> list[str]:
    reasons: list[str] = []
    if days_of_cover_delta is not None and days_of_cover_delta >= Decimal("0.5"):
        reasons.append("Days of cover increased by at least 0.5 days.")
    if shipment_delay_delta_hours is not None and shipment_delay_delta_hours <= Decimal("-6"):
        reasons.append("Shipment delay decreased by at least 6 hours.")
    if exposure_rank(current.exposure_level) < exposure_rank(previous.exposure_level):
        reasons.append("Exposure level improved.")
    return reasons


def escalation_score(
    state: str,
    current: ContinuityRiskSnapshot,
) -> Decimal:
    score = BASE_SCORES[state]
    if normalized(current.severity) == "critical":
        score += Decimal("5")
    if normalized(current.exposure_level) == "immediate":
        score += Decimal("5")
    if normalized(current.freshness_status) == "critical":
        score += Decimal("5")
    return min(max(score, Decimal("0")), Decimal("100"))


def is_blind_spot_risk(current: ContinuityRiskSnapshot) -> bool:
    return normalized(current.freshness_status) in {"stale", "critical"} and normalized(
        current.severity
    ) in {
        "high",
        "critical",
    }


def has_comparable_values(
    current: ContinuityRiskSnapshot,
    previous: ContinuityRiskSnapshot,
) -> bool:
    return any(
        [
            current.days_of_cover is not None and previous.days_of_cover is not None,
            current.shipment_delay_hours is not None
            and previous.shipment_delay_hours is not None,
            current.exposure_level is not None and previous.exposure_level is not None,
            current.severity is not None and previous.severity is not None,
        ]
    )


def delta(
    current: Decimal | None,
    previous: Decimal | None,
) -> Decimal | None:
    if current is None or previous is None:
        return None
    return current - previous


def severity_rank(severity: str | None) -> int:
    return SEVERITY_ORDER.get(normalized(severity), 0)


def exposure_rank(exposure_level: str | None) -> int:
    return EXPOSURE_ORDER.get(normalized(exposure_level or "unknown"), 0)


def normalized(value: str | None) -> str:
    return (value or "").strip().lower()
