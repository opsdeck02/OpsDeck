from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.models.enums import OperationalEventFreshnessStatus, OperationalEventSourceType


@dataclass(frozen=True)
class FreshnessThresholds:
    profile: str
    fresh_minutes: int
    delayed_minutes: int
    stale_minutes: int


@dataclass(frozen=True)
class FreshnessResult:
    status: OperationalEventFreshnessStatus
    age_minutes: int | None
    source_type: str
    threshold_profile: str
    reasons: list[str]


FILE_UPLOAD_THRESHOLDS = FreshnessThresholds(
    profile="file_upload",
    fresh_minutes=6 * 60,
    delayed_minutes=24 * 60,
    stale_minutes=72 * 60,
)
SYSTEM_INTEGRATION_THRESHOLDS = FreshnessThresholds(
    profile="system_integration",
    fresh_minutes=2 * 60,
    delayed_minutes=8 * 60,
    stale_minutes=24 * 60,
)
LOGISTICS_FEED_THRESHOLDS = FreshnessThresholds(
    profile="logistics_feed",
    fresh_minutes=60,
    delayed_minutes=6 * 60,
    stale_minutes=24 * 60,
)
EMAIL_MANUAL_THRESHOLDS = FreshnessThresholds(
    profile="email_manual",
    fresh_minutes=12 * 60,
    delayed_minutes=48 * 60,
    stale_minutes=96 * 60,
)
UNKNOWN_THRESHOLDS = FreshnessThresholds(
    profile="unknown",
    fresh_minutes=6 * 60,
    delayed_minutes=24 * 60,
    stale_minutes=72 * 60,
)


def classify_event_freshness(
    *,
    occurred_at: datetime | None,
    detected_at: datetime,
    source_type: OperationalEventSourceType,
) -> FreshnessResult:
    reasons: list[str] = []
    thresholds = thresholds_for_source_type(source_type)
    source_value = source_type.value

    if occurred_at is None:
        reasons.append("Occurred timestamp is missing; detected_at was used as the signal time")
        return FreshnessResult(
            status=OperationalEventFreshnessStatus.UNKNOWN,
            age_minutes=0,
            source_type=source_value,
            threshold_profile=thresholds.profile,
            reasons=reasons,
        )

    occurred = ensure_utc(occurred_at)
    detected = ensure_utc(detected_at)
    if occurred > detected:
        reasons.append("Occurred timestamp is after detected timestamp")
        return FreshnessResult(
            status=OperationalEventFreshnessStatus.UNKNOWN,
            age_minutes=None,
            source_type=source_value,
            threshold_profile=thresholds.profile,
            reasons=reasons,
        )

    age_minutes = int((detected - occurred).total_seconds() // 60)
    if source_type == OperationalEventSourceType.UNKNOWN and age_minutes > thresholds.fresh_minutes:
        reasons.append("Source type is unknown, so freshness is classified conservatively")
        return FreshnessResult(
            status=OperationalEventFreshnessStatus.UNKNOWN,
            age_minutes=age_minutes,
            source_type=source_value,
            threshold_profile=thresholds.profile,
            reasons=reasons,
        )

    status = status_for_age(age_minutes, thresholds)
    reasons.append(reason_for_status(status, thresholds))
    return FreshnessResult(
        status=status,
        age_minutes=age_minutes,
        source_type=source_value,
        threshold_profile=thresholds.profile,
        reasons=reasons,
    )


def thresholds_for_source_type(source_type: OperationalEventSourceType) -> FreshnessThresholds:
    if source_type in {
        OperationalEventSourceType.MANUAL_UPLOAD,
        OperationalEventSourceType.FILE_INGESTION,
        OperationalEventSourceType.EXTERNAL_DATA_SOURCE,
    }:
        return FILE_UPLOAD_THRESHOLDS
    if source_type in {
        OperationalEventSourceType.ERP,
        OperationalEventSourceType.WMS,
        OperationalEventSourceType.TMS,
    }:
        return SYSTEM_INTEGRATION_THRESHOLDS
    if source_type == OperationalEventSourceType.AIS:
        return LOGISTICS_FEED_THRESHOLDS
    if source_type in {
        OperationalEventSourceType.EMAIL_INGESTION,
        OperationalEventSourceType.MANUAL,
        OperationalEventSourceType.SUPPLIER_UPDATE,
    }:
        return EMAIL_MANUAL_THRESHOLDS
    return UNKNOWN_THRESHOLDS


def status_for_age(
    age_minutes: int,
    thresholds: FreshnessThresholds,
) -> OperationalEventFreshnessStatus:
    if age_minutes <= thresholds.fresh_minutes:
        return OperationalEventFreshnessStatus.FRESH
    if age_minutes <= thresholds.delayed_minutes:
        return OperationalEventFreshnessStatus.DELAYED
    if age_minutes <= thresholds.stale_minutes:
        return OperationalEventFreshnessStatus.STALE
    return OperationalEventFreshnessStatus.CRITICAL


def reason_for_status(
    status: OperationalEventFreshnessStatus,
    thresholds: FreshnessThresholds,
) -> str:
    if status == OperationalEventFreshnessStatus.FRESH:
        return f"Signal age is within the fresh threshold for {thresholds.profile}"
    if status == OperationalEventFreshnessStatus.DELAYED:
        return f"Signal age is within the delayed threshold for {thresholds.profile}"
    if status == OperationalEventFreshnessStatus.STALE:
        return f"Signal age is within the stale threshold for {thresholds.profile}"
    return f"Signal age exceeds the stale threshold for {thresholds.profile}"


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
