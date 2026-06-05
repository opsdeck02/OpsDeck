from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.stock.time_phased_cover import (
    TimePhasedCoverInputs,
    TimePhasedInbound,
    evaluate_time_phased_cover,
)


def test_time_phased_cover_marks_late_shipment_too_late() -> None:
    now = datetime(2026, 6, 1, tzinfo=UTC)

    result = evaluate_time_phased_cover(
        TimePhasedCoverInputs(
            snapshot_time=now,
            usable_stock_mt=Decimal("40"),
            daily_consumption_mt=Decimal("10"),
            warning_days=Decimal("5"),
            critical_days=Decimal("2"),
            reserve_days=Decimal("3"),
            reserve_quantity_mt=None,
            inbounds=(
                TimePhasedInbound(
                    shipment_id="SHP-A",
                    supplier_name="Supplier A",
                    eta=now + timedelta(hours=12),
                    raw_quantity_mt=Decimal("30"),
                    effective_quantity_mt=Decimal("30"),
                ),
                TimePhasedInbound(
                    shipment_id="SHP-B",
                    supplier_name="Supplier B",
                    eta=now + timedelta(days=8),
                    raw_quantity_mt=Decimal("30"),
                    effective_quantity_mt=Decimal("30"),
                ),
            ),
        )
    )

    assert result.calibration_status == "CALIBRATED"
    assert result.shipment_evaluations[0].shipment_id == "SHP-A"
    assert result.shipment_evaluations[0].protection_status == "PROTECTIVE"
    assert result.shipment_evaluations[0].protects_reserve_breach is True
    assert result.shipment_evaluations[1].shipment_id == "SHP-B"
    assert result.shipment_evaluations[1].protection_status == "TOO_LATE"


def test_time_phased_cover_marks_missing_assumptions_uncalibrated() -> None:
    now = datetime(2026, 6, 1, tzinfo=UTC)

    result = evaluate_time_phased_cover(
        TimePhasedCoverInputs(
            snapshot_time=now,
            usable_stock_mt=Decimal("100"),
            daily_consumption_mt=Decimal("10"),
            warning_days=None,
            critical_days=None,
            reserve_days=None,
            reserve_quantity_mt=None,
            interruption_configured=False,
            supplier_context_complete=False,
        )
    )

    assert result.calibration_status == "UNCALIBRATED"
    assert result.confidence_score < Decimal("1.00")
    assert "Warning threshold missing" in result.assumptions_used[0]
    assert any("Production interruption" in item for item in result.assumptions_used)


def test_time_phased_cover_handles_zero_consumption_without_breach_dates() -> None:
    now = datetime(2026, 6, 1, tzinfo=UTC)

    result = evaluate_time_phased_cover(
        TimePhasedCoverInputs(
            snapshot_time=now,
            usable_stock_mt=Decimal("100"),
            daily_consumption_mt=Decimal("0"),
            warning_days=Decimal("5"),
            critical_days=Decimal("2"),
            reserve_days=Decimal("3"),
            reserve_quantity_mt=None,
            inbounds=(),
        )
    )

    assert result.warning_date is None
    assert result.reserve_breach_date is None
    assert result.critical_breach_date is None
    assert result.interruption_date is None
    assert result.daily_projection[0].consumed_mt == Decimal("0.00")


def test_time_phased_cover_sequences_same_day_inbounds_chronologically() -> None:
    now = datetime(2026, 6, 1, 8, tzinfo=UTC)

    result = evaluate_time_phased_cover(
        TimePhasedCoverInputs(
            snapshot_time=now,
            usable_stock_mt=Decimal("40"),
            daily_consumption_mt=Decimal("10"),
            warning_days=Decimal("5"),
            critical_days=Decimal("2"),
            reserve_days=Decimal("3"),
            reserve_quantity_mt=None,
            inbounds=(
                TimePhasedInbound(
                    shipment_id="SHP-LATER",
                    supplier_name="Supplier",
                    eta=now + timedelta(hours=8),
                    raw_quantity_mt=Decimal("10"),
                    effective_quantity_mt=Decimal("10"),
                ),
                TimePhasedInbound(
                    shipment_id="SHP-EARLY",
                    supplier_name="Supplier",
                    eta=now + timedelta(hours=2),
                    raw_quantity_mt=Decimal("15"),
                    effective_quantity_mt=Decimal("15"),
                ),
            ),
        )
    )

    assert [item.shipment_id for item in result.shipment_evaluations] == [
        "SHP-EARLY",
        "SHP-LATER",
    ]
    assert result.daily_projection[0].inbound_received_mt == Decimal("25.00")


def test_time_phased_cover_does_not_count_low_confidence_quantity_at_raw_value() -> None:
    now = datetime(2026, 6, 1, tzinfo=UTC)

    result = evaluate_time_phased_cover(
        TimePhasedCoverInputs(
            snapshot_time=now,
            usable_stock_mt=Decimal("40"),
            daily_consumption_mt=Decimal("10"),
            warning_days=Decimal("5"),
            critical_days=Decimal("2"),
            reserve_days=Decimal("3"),
            reserve_quantity_mt=None,
            inbounds=(
                TimePhasedInbound(
                    shipment_id="LOW-CONFIDENCE",
                    supplier_name="Supplier",
                    eta=now + timedelta(days=1),
                    raw_quantity_mt=Decimal("100"),
                    effective_quantity_mt=Decimal("20"),
                ),
            ),
        )
    )

    shipment = result.shipment_evaluations[0]
    assert shipment.raw_quantity_mt == Decimal("100.00")
    assert shipment.effective_quantity_mt == Decimal("20.00")
    assert shipment.stock_after_arrival_mt == Decimal("50.00")


def test_time_phased_cover_preserves_reserve_breach_before_recovery() -> None:
    now = datetime(2026, 6, 1, tzinfo=UTC)

    result = evaluate_time_phased_cover(
        TimePhasedCoverInputs(
            snapshot_time=now,
            usable_stock_mt=Decimal("35"),
            daily_consumption_mt=Decimal("10"),
            warning_days=Decimal("5"),
            critical_days=Decimal("2"),
            reserve_days=Decimal("3"),
            reserve_quantity_mt=None,
            inbounds=(
                TimePhasedInbound(
                    shipment_id="RECOVERY",
                    supplier_name="Supplier",
                    eta=now + timedelta(days=1),
                    raw_quantity_mt=Decimal("50"),
                    effective_quantity_mt=Decimal("50"),
                ),
            ),
        )
    )

    assert result.reserve_breach_date == now + timedelta(hours=12)
    assert result.current_projected_reserve_breach_date == now + timedelta(days=5, hours=12)
    assert result.shipment_evaluations[0].protection_status == "LATE_AFTER_RESERVE"


def test_time_phased_cover_preserves_critical_breach_before_recovery() -> None:
    now = datetime(2026, 6, 1, tzinfo=UTC)

    result = evaluate_time_phased_cover(
        TimePhasedCoverInputs(
            snapshot_time=now,
            usable_stock_mt=Decimal("25"),
            daily_consumption_mt=Decimal("10"),
            warning_days=Decimal("5"),
            critical_days=Decimal("2"),
            reserve_days=Decimal("3"),
            reserve_quantity_mt=None,
            inbounds=(
                TimePhasedInbound(
                    shipment_id="RECOVERY",
                    supplier_name="Supplier",
                    eta=now + timedelta(days=1),
                    raw_quantity_mt=Decimal("50"),
                    effective_quantity_mt=Decimal("50"),
                ),
            ),
        )
    )

    assert result.critical_breach_date == now + timedelta(hours=12)
    assert result.current_projected_critical_breach_date == now + timedelta(days=5, hours=12)
    assert result.shipment_evaluations[0].protection_status == "TOO_LATE"


def test_time_phased_cover_preserves_interruption_before_recovery() -> None:
    now = datetime(2026, 6, 1, tzinfo=UTC)

    result = evaluate_time_phased_cover(
        TimePhasedCoverInputs(
            snapshot_time=now,
            usable_stock_mt=Decimal("5"),
            daily_consumption_mt=Decimal("10"),
            warning_days=Decimal("5"),
            critical_days=Decimal("2"),
            reserve_days=Decimal("3"),
            reserve_quantity_mt=None,
            inbounds=(
                TimePhasedInbound(
                    shipment_id="RECOVERY",
                    supplier_name="Supplier",
                    eta=now + timedelta(days=1),
                    raw_quantity_mt=Decimal("50"),
                    effective_quantity_mt=Decimal("50"),
                ),
            ),
        )
    )

    assert result.interruption_date == now + timedelta(hours=12)
    assert result.current_projected_interruption_date == now + timedelta(days=6)
    assert result.shipment_evaluations[0].protection_status == "TOO_LATE"


def test_time_phased_cover_sequences_multiple_recovery_shipments() -> None:
    now = datetime(2026, 6, 1, tzinfo=UTC)

    result = evaluate_time_phased_cover(
        TimePhasedCoverInputs(
            snapshot_time=now,
            usable_stock_mt=Decimal("40"),
            daily_consumption_mt=Decimal("10"),
            warning_days=Decimal("5"),
            critical_days=Decimal("2"),
            reserve_days=Decimal("3"),
            reserve_quantity_mt=None,
            inbounds=(
                TimePhasedInbound(
                    shipment_id="FIRST",
                    supplier_name="Supplier",
                    eta=now + timedelta(hours=6),
                    raw_quantity_mt=Decimal("10"),
                    effective_quantity_mt=Decimal("10"),
                ),
                TimePhasedInbound(
                    shipment_id="SECOND",
                    supplier_name="Supplier",
                    eta=now + timedelta(days=1),
                    raw_quantity_mt=Decimal("30"),
                    effective_quantity_mt=Decimal("30"),
                ),
            ),
        )
    )

    assert result.reserve_breach_date == result.current_projected_reserve_breach_date
    assert result.current_projected_reserve_breach_date == now + timedelta(days=5)
    assert result.first_reserve_protecting_shipment_id == "FIRST"
    assert result.shipment_evaluations[1].protection_status == "PROTECTIVE"


def test_time_phased_cover_same_day_recovery_preserves_first_breach() -> None:
    now = datetime(2026, 6, 1, 8, tzinfo=UTC)

    result = evaluate_time_phased_cover(
        TimePhasedCoverInputs(
            snapshot_time=now,
            usable_stock_mt=Decimal("35"),
            daily_consumption_mt=Decimal("10"),
            warning_days=Decimal("5"),
            critical_days=Decimal("2"),
            reserve_days=Decimal("3"),
            reserve_quantity_mt=None,
            inbounds=(
                TimePhasedInbound(
                    shipment_id="SAME-DAY-RECOVERY",
                    supplier_name="Supplier",
                    eta=now + timedelta(hours=18),
                    raw_quantity_mt=Decimal("40"),
                    effective_quantity_mt=Decimal("40"),
                ),
            ),
        )
    )

    assert result.reserve_breach_date == now + timedelta(hours=12)
    assert result.current_projected_reserve_breach_date == now + timedelta(days=4, hours=12)


def test_time_phased_cover_without_inbound_has_same_first_and_current_dates() -> None:
    now = datetime(2026, 6, 1, tzinfo=UTC)

    result = evaluate_time_phased_cover(
        TimePhasedCoverInputs(
            snapshot_time=now,
            usable_stock_mt=Decimal("100"),
            daily_consumption_mt=Decimal("10"),
            warning_days=Decimal("5"),
            critical_days=Decimal("2"),
            reserve_days=Decimal("3"),
            reserve_quantity_mt=None,
            inbounds=(),
        )
    )

    assert result.warning_date == result.current_projected_warning_date
    assert result.reserve_breach_date == result.current_projected_reserve_breach_date
    assert result.critical_breach_date == result.current_projected_critical_breach_date
    assert result.interruption_date == result.current_projected_interruption_date
