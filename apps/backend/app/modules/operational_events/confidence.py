from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.models.enums import OperationalEventCategory, OperationalEventSourceType
from app.modules.operational_events.schemas import OperationalEventCreate

SOURCE_RELIABILITY = {
    OperationalEventSourceType.MANUAL: 70,
    OperationalEventSourceType.MANUAL_UPLOAD: 80,
    OperationalEventSourceType.FILE_INGESTION: 80,
    OperationalEventSourceType.ERP: 90,
    OperationalEventSourceType.WMS: 90,
    OperationalEventSourceType.TMS: 90,
    OperationalEventSourceType.AIS: 85,
    OperationalEventSourceType.EXTERNAL_DATA_SOURCE: 80,
    OperationalEventSourceType.EMAIL_INGESTION: 65,
    OperationalEventSourceType.SUPPLIER_UPDATE: 75,
    OperationalEventSourceType.SYSTEM: 85,
    OperationalEventSourceType.UNKNOWN: 50,
}

WEIGHTS = {
    "source_reliability": Decimal("0.30"),
    "freshness": Decimal("0.25"),
    "completeness": Decimal("0.25"),
    "validation": Decimal("0.20"),
}


@dataclass(frozen=True)
class ConfidenceResult:
    score: Decimal
    factors: dict[str, int]
    reasons: list[str]


def calculate_confidence(
    payload: OperationalEventCreate,
    detected_at: datetime,
) -> ConfidenceResult:
    factors: dict[str, int] = {}
    reasons: list[str] = []
    factors["source_reliability"] = source_reliability_score(payload.source_type, reasons)
    factors["freshness"] = freshness_score(payload.occurred_at, detected_at, reasons)
    factors["completeness"] = completeness_score(payload, reasons)
    factors["validation"] = validation_score(payload, detected_at, reasons)

    score = sum(Decimal(factors[name]) * weight for name, weight in WEIGHTS.items())
    score = max(Decimal("0"), min(Decimal("100"), score)).quantize(Decimal("0.01"))
    return ConfidenceResult(score=score, factors=factors, reasons=reasons)


def source_reliability_score(
    source_type: OperationalEventSourceType,
    reasons: list[str],
) -> int:
    score = SOURCE_RELIABILITY.get(source_type, 50)
    if source_type == OperationalEventSourceType.UNKNOWN:
        reasons.append("Source type is unknown, so source reliability is low")
    elif score >= 85:
        reasons.append(f"Source type {source_type.value} has high reliability")
    elif score >= 75:
        reasons.append(f"Source type {source_type.value} has medium-high reliability")
    else:
        reasons.append(f"Source type {source_type.value} has limited reliability")
    return score


def freshness_score(
    occurred_at: datetime | None,
    detected_at: datetime,
    reasons: list[str],
) -> int:
    if occurred_at is None:
        reasons.append("Occurred timestamp is missing")
        return 40
    occurred = ensure_utc(occurred_at)
    detected = ensure_utc(detected_at)
    age_hours = (detected - occurred).total_seconds() / 3600
    if age_hours < 0:
        reasons.append("Occurred timestamp is after detected timestamp")
        return 45
    if age_hours <= 24:
        reasons.append("Signal detected within expected freshness window")
        return 95
    if age_hours <= 72:
        reasons.append("Signal is recent but outside the freshest window")
        return 85
    if age_hours <= 168:
        reasons.append("Signal is aging based on occurred timestamp")
        return 70
    if age_hours <= 720:
        reasons.append("Signal is stale based on occurred timestamp")
        return 55
    reasons.append("Signal is very old based on occurred timestamp")
    return 35


def completeness_score(payload: OperationalEventCreate, reasons: list[str]) -> int:
    fields = completeness_fields(payload.event_category)
    if not fields:
        reasons.append("No category-specific completeness fields required")
        return 80

    present = sum(1 for field in fields if has_value(getattr(payload, field)))
    score = int(round((present / len(fields)) * 100))
    present_names = [field for field in fields if has_value(getattr(payload, field))]
    missing_names = [field for field in fields if not has_value(getattr(payload, field))]
    if present_names:
        reasons.append(f"Category references present: {', '.join(present_names)}")
    if missing_names:
        reasons.append(f"Missing category references: {', '.join(missing_names)}")
    return score


def completeness_fields(category: OperationalEventCategory) -> tuple[str, ...]:
    if category == OperationalEventCategory.INVENTORY:
        return ("plant_reference", "material_reference", "quantity_value", "quantity_unit")
    if category == OperationalEventCategory.SHIPMENT:
        return (
            "shipment_reference",
            "plant_reference",
            "material_reference",
            "supplier_reference",
            "quantity_value",
            "quantity_unit",
        )
    if category == OperationalEventCategory.SUPPLIER:
        return ("supplier_reference",)
    if category == OperationalEventCategory.PLANNING:
        return ("plant_reference", "material_reference")
    if category == OperationalEventCategory.PRODUCTION:
        return ("plant_reference", "material_reference")
    return ()


def validation_score(
    payload: OperationalEventCreate,
    detected_at: datetime,
    reasons: list[str],
) -> int:
    score = 100
    if payload.source_type == OperationalEventSourceType.UNKNOWN:
        score -= 25
    if payload.occurred_at and ensure_utc(payload.occurred_at) > ensure_utc(detected_at):
        score -= 25
    if payload.quantity_value is not None and payload.quantity_value < 0:
        score -= 25
        reasons.append("Quantity value is negative")
    if payload.event_category == OperationalEventCategory.INVENTORY:
        for field in ("plant_reference", "material_reference"):
            if not has_value(getattr(payload, field)):
                score -= 15
    if payload.event_category == OperationalEventCategory.SHIPMENT:
        for field in ("shipment_reference", "plant_reference", "material_reference"):
            if not has_value(getattr(payload, field)):
                score -= 15
    if score == 100:
        reasons.append("Required category fields and values passed validation")
    else:
        reasons.append("Validation checks found missing or lower-quality fields")
    return max(0, score)


def has_value(value) -> bool:
    return value is not None and value != ""


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
