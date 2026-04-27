from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.modules.impact.config import get_impact_config

CONFIDENCE_IMPACT_FACTORS = {
    "high": Decimal("1.00"),
    "medium": Decimal("0.90"),
    "low": Decimal("0.75"),
}


@dataclass(frozen=True)
class ImpactEstimate:
    risk_hours_remaining: Decimal | None
    estimated_production_exposure_mt: Decimal | None
    estimated_value_at_risk: Decimal | None
    value_per_mt_used: Decimal | None
    criticality_multiplier_used: Decimal | None
    urgency_band: str
    explanation: list[str]


def calculate_impact(
    *,
    plant_code: str,
    material_code: str,
    days_of_cover: Decimal | None,
    status: str,
    threshold_days: Decimal | None,
    warning_days: Decimal | None,
    daily_consumption_mt: Decimal | None,
    effective_inbound_pipeline_mt: Decimal,
    confidence_level: str,
    elapsed_hours_since_snapshot: Decimal | None = None,
) -> ImpactEstimate:
    elapsed_hours = elapsed_hours_since_snapshot or Decimal("0")
    risk_hours_remaining = (
        quantize_decimal(max((days_of_cover * Decimal("24")) - elapsed_hours, Decimal("0")))
        if days_of_cover is not None
        else None
    )
    effective_days_of_cover = (
        quantize_decimal(risk_hours_remaining / Decimal("24"))
        if risk_hours_remaining is not None
        else None
    )
    urgency_band = determine_urgency_band(status, effective_days_of_cover, risk_hours_remaining)

    if days_of_cover is None or daily_consumption_mt is None:
        return ImpactEstimate(
            risk_hours_remaining=risk_hours_remaining,
            estimated_production_exposure_mt=None,
            estimated_value_at_risk=None,
            value_per_mt_used=None,
            criticality_multiplier_used=None,
            urgency_band=urgency_band,
            explanation=[
                "Impact could not be calculated because cover days or daily consumption is missing."
            ],
        )

    config = get_impact_config(plant_code, material_code)
    confidence_factor = CONFIDENCE_IMPACT_FACTORS.get(confidence_level, Decimal("0.75"))
    severity_days = severity_days_for(
        status,
        effective_days_of_cover or Decimal("0"),
        threshold_days,
        warning_days,
    )
    estimated_production_exposure_mt = quantize_decimal(
        daily_consumption_mt
        * severity_days
        * config["criticality_multiplier"]
        * confidence_factor
    )
    estimated_value_at_risk = quantize_decimal(
        estimated_production_exposure_mt * config["value_per_mt"]
    )

    explanation = [
        (
            f"Risk hours remaining = ({quantize_decimal(days_of_cover)} days x 24) - "
            f"{quantize_decimal(elapsed_hours)} elapsed hours since the latest snapshot."
        ),
        (
            "Production exposure = daily consumption x breach severity x criticality multiplier "
            f"x confidence factor ({confidence_factor})."
        ),
        (
            f"Value at risk = exposed MT x configured value/MT "
            f"({quantize_decimal(config['value_per_mt'])})."
        ),
        f"Effective inbound pipeline considered: {quantize_decimal(effective_inbound_pipeline_mt)} MT.",
    ]

    return ImpactEstimate(
        risk_hours_remaining=risk_hours_remaining,
        estimated_production_exposure_mt=estimated_production_exposure_mt,
        estimated_value_at_risk=estimated_value_at_risk,
        value_per_mt_used=quantize_decimal(config["value_per_mt"]),
        criticality_multiplier_used=quantize_decimal(config["criticality_multiplier"]),
        urgency_band=urgency_band,
        explanation=explanation,
    )


def severity_days_for(
    status: str,
    days_of_cover: Decimal,
    threshold_days: Decimal | None,
    warning_days: Decimal | None,
) -> Decimal:
    if status == "critical" and threshold_days is not None:
        return max(Decimal("0"), threshold_days - days_of_cover)
    if status == "warning" and warning_days is not None:
        return max(Decimal("0"), warning_days - days_of_cover)
    return Decimal("0")


def determine_urgency_band(
    status: str,
    days_of_cover: Decimal | None,
    risk_hours_remaining: Decimal | None,
) -> str:
    if status in {"safe", "insufficient_data"} or risk_hours_remaining is None:
        return "monitor"
    if days_of_cover is not None and days_of_cover <= Decimal("1"):
        return "immediate"
    if risk_hours_remaining <= Decimal("24"):
        return "next_24h"
    if risk_hours_remaining <= Decimal("72") or status == "critical":
        return "next_72h"
    return "monitor"


def quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
