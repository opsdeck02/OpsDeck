from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.modules.stock.schemas import (
    DailyStockProjection,
    ShipmentProtectionEvaluation,
    TimePhasedCoverResult,
)

DEFAULT_WARNING_DAYS = Decimal("5")
DEFAULT_CRITICAL_DAYS = Decimal("2")
DEFAULT_RESERVE_DAYS = Decimal("2")
DEFAULT_HORIZON_DAYS = 30


@dataclass(frozen=True)
class TimePhasedInbound:
    shipment_id: str
    supplier_name: str
    eta: datetime
    raw_quantity_mt: Decimal
    effective_quantity_mt: Decimal
    supplier_linked: bool = True


@dataclass(frozen=True)
class TimePhasedCoverInputs:
    snapshot_time: datetime
    usable_stock_mt: Decimal
    daily_consumption_mt: Decimal
    warning_days: Decimal | None
    critical_days: Decimal | None
    reserve_days: Decimal | None
    reserve_quantity_mt: Decimal | None
    interruption_configured: bool = True
    supplier_context_complete: bool = True
    inbounds: tuple[TimePhasedInbound, ...] = ()
    horizon_days: int = DEFAULT_HORIZON_DAYS


@dataclass(frozen=True)
class BreachDates:
    warning_date: datetime | None
    reserve_breach_date: datetime | None
    critical_breach_date: datetime | None
    interruption_date: datetime | None


def evaluate_time_phased_cover(inputs: TimePhasedCoverInputs) -> TimePhasedCoverResult:
    evaluated_at = ensure_utc(inputs.snapshot_time)
    assumptions = calibration_assumptions(inputs)
    warning_days = inputs.warning_days or DEFAULT_WARNING_DAYS
    critical_days = inputs.critical_days or DEFAULT_CRITICAL_DAYS
    reserve_days = inputs.reserve_days or DEFAULT_RESERVE_DAYS
    reserve_threshold_mt = reserve_threshold_quantity(
        daily_consumption=inputs.daily_consumption_mt,
        reserve_days=reserve_days,
        reserve_quantity=inputs.reserve_quantity_mt,
    )
    warning_threshold_mt = inputs.daily_consumption_mt * warning_days
    critical_threshold_mt = inputs.daily_consumption_mt * critical_days

    confidence = confidence_score(assumptions)
    calibration_status = "UNCALIBRATED" if assumptions else "CALIBRATED"
    ordered_inbounds = sorted(inputs.inbounds, key=lambda item: ensure_utc(item.eta))
    baseline_dates = breach_dates_from(
        start_time=evaluated_at,
        stock_mt=inputs.usable_stock_mt,
        daily_consumption=inputs.daily_consumption_mt,
        warning_threshold_mt=warning_threshold_mt,
        reserve_threshold_mt=reserve_threshold_mt,
        critical_threshold_mt=critical_threshold_mt,
    )

    cursor_time = evaluated_at
    stock = inputs.usable_stock_mt
    evaluations: list[ShipmentProtectionEvaluation] = []
    first_reserve_protector: str | None = None
    first_interruption_protector: str | None = None
    current_dates = baseline_dates
    first_dates = BreachDates(
        warning_date=None,
        reserve_breach_date=None,
        critical_breach_date=None,
        interruption_date=None,
    )

    for inbound in ordered_inbounds:
        eta = ensure_utc(inbound.eta)
        if eta < cursor_time:
            eta = cursor_time
        first_dates = merge_breach_dates(
            first_dates,
            bounded_breach_dates(current_dates, latest_time=eta),
        )
        stock_before = stock_after_consumption(
            stock,
            daily_consumption=inputs.daily_consumption_mt,
            from_time=cursor_time,
            to_time=eta,
        )
        status, reasons = protection_status(
            eta=eta,
            dates_before=current_dates,
            stock_before=stock_before,
            critical_threshold_mt=critical_threshold_mt,
            reserve_threshold_mt=reserve_threshold_mt,
        )
        stock_after = stock_before + inbound.effective_quantity_mt
        dates_after = breach_dates_from(
            start_time=eta,
            stock_mt=stock_after,
            daily_consumption=inputs.daily_consumption_mt,
            warning_threshold_mt=warning_threshold_mt,
            reserve_threshold_mt=reserve_threshold_mt,
            critical_threshold_mt=critical_threshold_mt,
        )
        protects_reserve = breach_extended(
            before=current_dates.reserve_breach_date,
            after=dates_after.reserve_breach_date,
        )
        protects_interruption = breach_extended(
            before=current_dates.interruption_date,
            after=dates_after.interruption_date,
        )
        if protects_reserve and first_reserve_protector is None:
            first_reserve_protector = inbound.shipment_id
            reasons.append("This is the first inbound that extends reserve-breach protection.")
        if protects_interruption and first_interruption_protector is None:
            first_interruption_protector = inbound.shipment_id
            reasons.append("This is the first inbound that extends interruption protection.")
        if not inbound.supplier_linked:
            reasons.append(
                "Supplier is not linked to supplier master; supplier reliability context "
                "is missing."
            )

        evaluations.append(
            ShipmentProtectionEvaluation(
                shipment_id=inbound.shipment_id,
                supplier_name=inbound.supplier_name,
                eta=eta,
                raw_quantity_mt=quantize_decimal(inbound.raw_quantity_mt),
                effective_quantity_mt=quantize_decimal(inbound.effective_quantity_mt),
                stock_before_arrival_mt=quantize_decimal(stock_before),
                stock_after_arrival_mt=quantize_decimal(stock_after),
                protection_status=status,
                protects_reserve_breach=protects_reserve,
                protects_interruption=protects_interruption,
                reasoning=reasons,
            )
        )
        stock = stock_after
        cursor_time = eta
        current_dates = dates_after

    current_projected_dates = current_dates
    first_dates = merge_breach_dates(first_dates, current_projected_dates)
    projection = daily_projection(
        start_time=evaluated_at,
        starting_stock=inputs.usable_stock_mt,
        daily_consumption=inputs.daily_consumption_mt,
        inbounds=ordered_inbounds,
        horizon_days=inputs.horizon_days,
    )
    reasoning = [
        "Projected stock position is calculated chronologically from the latest stock snapshot.",
        "Inbound shipments are sorted by ETA and added only when they arrive.",
        "First breach dates preserve the earliest threshold breach even if later inbound "
        "recovers stock.",
        "Current projected dates show the post-recovery state after sequenced inbound is applied.",
        "Shipment protection is evaluated against warning, reserve, critical, and "
        "interruption dates.",
    ]
    if assumptions:
        reasoning.append(
            "Result is UNCALIBRATED because required operational assumptions are missing."
        )

    return TimePhasedCoverResult(
        calibration_status=calibration_status,
        confidence_score=confidence,
        assumptions_used=assumptions,
        warning_date=first_dates.warning_date,
        reserve_breach_date=first_dates.reserve_breach_date,
        critical_breach_date=first_dates.critical_breach_date,
        interruption_date=first_dates.interruption_date,
        current_projected_warning_date=current_projected_dates.warning_date,
        current_projected_reserve_breach_date=current_projected_dates.reserve_breach_date,
        current_projected_critical_breach_date=current_projected_dates.critical_breach_date,
        current_projected_interruption_date=current_projected_dates.interruption_date,
        first_reserve_protecting_shipment_id=first_reserve_protector,
        first_interruption_protecting_shipment_id=first_interruption_protector,
        daily_projection=projection,
        shipment_evaluations=evaluations,
        reasoning=reasoning,
    )


def calibration_assumptions(inputs: TimePhasedCoverInputs) -> list[str]:
    assumptions: list[str] = []
    if inputs.warning_days is None:
        assumptions.append(f"Warning threshold missing; assumed {DEFAULT_WARNING_DAYS} days.")
    if inputs.critical_days is None:
        assumptions.append(f"Critical threshold missing; assumed {DEFAULT_CRITICAL_DAYS} days.")
    if inputs.reserve_days is None and inputs.reserve_quantity_mt is None:
        assumptions.append(f"Reserve threshold missing; assumed {DEFAULT_RESERVE_DAYS} days.")
    if not inputs.interruption_configured:
        assumptions.append("Production interruption impact configuration is missing.")
    if not inputs.supplier_context_complete:
        assumptions.append("One or more inbound shipments are missing supplier master linkage.")
    return assumptions


def confidence_score(assumptions: list[str]) -> Decimal:
    score = Decimal("1.00") - Decimal("0.15") * Decimal(len(assumptions))
    return quantize_decimal(max(Decimal("0.25"), score))


def reserve_threshold_quantity(
    *,
    daily_consumption: Decimal,
    reserve_days: Decimal,
    reserve_quantity: Decimal | None,
) -> Decimal:
    reserve_from_days = daily_consumption * reserve_days
    if reserve_quantity is None:
        return reserve_from_days
    return max(reserve_from_days, reserve_quantity)


def breach_dates_from(
    *,
    start_time: datetime,
    stock_mt: Decimal,
    daily_consumption: Decimal,
    warning_threshold_mt: Decimal,
    reserve_threshold_mt: Decimal,
    critical_threshold_mt: Decimal,
) -> BreachDates:
    return BreachDates(
        warning_date=date_when_stock_reaches(
            start_time, stock_mt, daily_consumption, warning_threshold_mt
        ),
        reserve_breach_date=date_when_stock_reaches(
            start_time, stock_mt, daily_consumption, reserve_threshold_mt
        ),
        critical_breach_date=date_when_stock_reaches(
            start_time, stock_mt, daily_consumption, critical_threshold_mt
        ),
        interruption_date=date_when_stock_reaches(
            start_time, stock_mt, daily_consumption, Decimal("0")
        ),
    )


def bounded_breach_dates(dates: BreachDates, *, latest_time: datetime) -> BreachDates:
    latest = ensure_utc(latest_time)
    return BreachDates(
        warning_date=dates.warning_date if date_on_or_before(dates.warning_date, latest) else None,
        reserve_breach_date=dates.reserve_breach_date
        if date_on_or_before(dates.reserve_breach_date, latest)
        else None,
        critical_breach_date=dates.critical_breach_date
        if date_on_or_before(dates.critical_breach_date, latest)
        else None,
        interruption_date=dates.interruption_date
        if date_on_or_before(dates.interruption_date, latest)
        else None,
    )


def merge_breach_dates(existing: BreachDates, candidate: BreachDates) -> BreachDates:
    return BreachDates(
        warning_date=earliest_date(existing.warning_date, candidate.warning_date),
        reserve_breach_date=earliest_date(
            existing.reserve_breach_date,
            candidate.reserve_breach_date,
        ),
        critical_breach_date=earliest_date(
            existing.critical_breach_date,
            candidate.critical_breach_date,
        ),
        interruption_date=earliest_date(existing.interruption_date, candidate.interruption_date),
    )


def earliest_date(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(ensure_utc(left), ensure_utc(right))


def date_on_or_before(value: datetime | None, latest: datetime) -> bool:
    return value is not None and ensure_utc(value) <= latest


def protection_status(
    *,
    eta: datetime,
    dates_before: BreachDates,
    stock_before: Decimal,
    critical_threshold_mt: Decimal,
    reserve_threshold_mt: Decimal,
) -> tuple[str, list[str]]:
    if dates_before.interruption_date is not None and eta > dates_before.interruption_date:
        return (
            "TOO_LATE",
            ["Shipment arrives after projected interruption date; it does not protect continuity."],
        )
    if dates_before.critical_breach_date is not None and eta > dates_before.critical_breach_date:
        return (
            "TOO_LATE",
            ["Shipment arrives after projected critical breach date."],
        )
    if dates_before.reserve_breach_date is not None and eta > dates_before.reserve_breach_date:
        return (
            "LATE_AFTER_RESERVE",
            ["Shipment arrives after projected reserve breach but before critical breach."],
        )
    if stock_before <= critical_threshold_mt:
        return (
            "CRITICAL_ON_ARRIVAL",
            ["Shipment arrives while projected stock is already at or below critical level."],
        )
    if stock_before <= reserve_threshold_mt:
        return (
            "RESERVE_ON_ARRIVAL",
            ["Shipment arrives while projected stock is already at or below reserve level."],
        )
    return (
        "PROTECTIVE",
        ["Shipment arrives before reserve breach and protects continuity timing."],
    )


def breach_extended(before: datetime | None, after: datetime | None) -> bool:
    if before is None:
        return False
    if after is None:
        return True
    return after > before


def daily_projection(
    *,
    start_time: datetime,
    starting_stock: Decimal,
    daily_consumption: Decimal,
    inbounds: list[TimePhasedInbound],
    horizon_days: int,
) -> list[DailyStockProjection]:
    projection: list[DailyStockProjection] = []
    stock = starting_stock
    start_day = ensure_utc(start_time)
    for day_offset in range(max(0, horizon_days)):
        day_start = start_day + timedelta(days=day_offset)
        day_end = day_start + timedelta(days=1)
        inbound_quantity = sum(
            (
                inbound.effective_quantity_mt
                for inbound in inbounds
                if day_start <= ensure_utc(inbound.eta) < day_end
            ),
            start=Decimal("0"),
        )
        opening = stock
        stock = max(Decimal("0"), stock + inbound_quantity - daily_consumption)
        projection.append(
            DailyStockProjection(
                projection_date=day_start,
                opening_stock_mt=quantize_decimal(opening),
                inbound_received_mt=quantize_decimal(inbound_quantity),
                consumed_mt=quantize_decimal(daily_consumption),
                closing_stock_mt=quantize_decimal(stock),
            )
        )
    return projection


def date_when_stock_reaches(
    start_time: datetime,
    stock_mt: Decimal,
    daily_consumption: Decimal,
    threshold_mt: Decimal,
) -> datetime | None:
    if daily_consumption <= 0:
        return None
    if stock_mt <= threshold_mt:
        return ensure_utc(start_time)
    days = (stock_mt - threshold_mt) / daily_consumption
    return ensure_utc(start_time) + timedelta(days=float(days))


def stock_after_consumption(
    stock_mt: Decimal,
    *,
    daily_consumption: Decimal,
    from_time: datetime,
    to_time: datetime,
) -> Decimal:
    elapsed_days = Decimal(str((ensure_utc(to_time) - ensure_utc(from_time)).total_seconds()))
    elapsed_days = max(Decimal("0"), elapsed_days / Decimal("86400"))
    return max(Decimal("0"), stock_mt - daily_consumption * elapsed_days)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
