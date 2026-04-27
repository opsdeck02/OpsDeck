from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True)
class FreshnessAssessment:
    last_updated_at: datetime | None
    freshness_hours: Decimal | None
    freshness_label: str


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def ensure_optional_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return ensure_utc(value)


def assess_freshness(last_updated_at: datetime | None) -> FreshnessAssessment:
    if last_updated_at is None:
        return FreshnessAssessment(
            last_updated_at=None,
            freshness_hours=None,
            freshness_label="unknown",
        )

    last_seen = ensure_utc(last_updated_at)
    hours = quantize_decimal(
        Decimal((datetime.now(UTC) - last_seen).total_seconds()) / Decimal("3600")
    )
    if hours <= Decimal("24"):
        label = "fresh"
    elif hours <= Decimal("72"):
        label = "aging"
    else:
        label = "stale"

    return FreshnessAssessment(
        last_updated_at=last_seen,
        freshness_hours=hours,
        freshness_label=label,
    )


def evaluate_confidence(
    *,
    freshness: FreshnessAssessment,
    total_fields: int,
    present_fields: int,
    has_conflict: bool = False,
    missing_fields: list[str] | None = None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    missing = missing_fields or []

    if freshness.last_updated_at is None:
        reasons.append("No recent source timestamp is available.")
    elif freshness.freshness_label == "fresh":
        reasons.append("Source data was updated in the last 24 hours.")
    elif freshness.freshness_label == "aging":
        reasons.append("Source data is aging and should be refreshed soon.")
    else:
        reasons.append("Source data is stale.")

    if has_conflict:
        reasons.append("Signals conflict across shipment, port, or inland records.")
    if missing:
        reasons.append(f"Missing fields: {', '.join(missing)}.")

    ratio = present_fields / total_fields if total_fields else 0
    if has_conflict or freshness.freshness_label == "stale":
        return "low", reasons
    if freshness.freshness_label == "fresh" and ratio >= 0.75 and not missing:
        return "high", reasons
    if ratio >= 0.5:
        return "medium", reasons
    return "low", reasons


def quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))
