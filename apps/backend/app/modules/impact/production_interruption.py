from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProductionInterruptionImpactConfig
from app.modules.impact.schemas import OperationalInterruptionImpact

FORMULA_VERSION = "production_interruption_impact_v1"
DEFAULT_CURRENCY = "INR"
REQUIRED_CONFIG_FIELDS = [
    "production_rate_mt_per_hour",
    "finished_goods_value_per_mt",
    "survivable_hours_without_material",
    "line_dependency_ratio",
    "downtime_cost_per_hour",
    "restart_cost",
    "restart_time_hours",
    "substitution_factor",
    "cascading_impact_factor",
]

URGENCY_PROBABILITIES = {
    "immediate": Decimal("0.75"),
    "next_24h": Decimal("0.65"),
    "next_72h": Decimal("0.45"),
    "near_term": Decimal("0.35"),
    "watch": Decimal("0.20"),
    "monitor": Decimal("0.10"),
    "unknown": Decimal("0.10"),
    "safe": Decimal("0.10"),
}


@dataclass(frozen=True)
class ProductionInterruptionInputs:
    tenant_id: int
    plant_id: int
    material_id: int
    material_exposure_value: Decimal | None
    days_of_cover: Decimal | None
    risk_hours_remaining: Decimal | None
    urgency_band: str
    continuity_severity: str
    projected_exhaustion_date: datetime | None = None
    next_trusted_inbound_eta: datetime | None = None
    trusted_inbound_ratio: Decimal | None = None
    shipment_confidence_low: bool = False
    freshness_status: str | None = None


def get_active_interruption_config(
    db: Session,
    *,
    tenant_id: int,
    plant_id: int,
    material_id: int,
    production_line_id: int | None = None,
) -> ProductionInterruptionImpactConfig | None:
    if production_line_id is not None:
        exact_config = db.scalar(
            select(ProductionInterruptionImpactConfig)
            .where(
                ProductionInterruptionImpactConfig.tenant_id == tenant_id,
                ProductionInterruptionImpactConfig.plant_id == plant_id,
                ProductionInterruptionImpactConfig.material_id == material_id,
                ProductionInterruptionImpactConfig.production_line_id == production_line_id,
                ProductionInterruptionImpactConfig.is_active.is_(True),
            )
            .order_by(
                ProductionInterruptionImpactConfig.updated_at.desc(),
                ProductionInterruptionImpactConfig.id.desc(),
            )
        )
        if exact_config is not None:
            return exact_config

    return db.scalar(
        select(ProductionInterruptionImpactConfig)
        .where(
            ProductionInterruptionImpactConfig.tenant_id == tenant_id,
            ProductionInterruptionImpactConfig.plant_id == plant_id,
            ProductionInterruptionImpactConfig.material_id == material_id,
            ProductionInterruptionImpactConfig.production_line_id.is_(None),
            ProductionInterruptionImpactConfig.is_active.is_(True),
        )
        .order_by(
            ProductionInterruptionImpactConfig.updated_at.desc(),
            ProductionInterruptionImpactConfig.id.desc(),
        )
    )


def calculate_production_interruption_impact(
    inputs: ProductionInterruptionInputs,
    config: ProductionInterruptionImpactConfig | None,
) -> OperationalInterruptionImpact:
    if inputs.risk_hours_remaining is None:
        if inputs.days_of_cover is None:
            return unavailable_result(
                material_exposure_value=inputs.material_exposure_value,
                status="insufficient_data",
                currency=DEFAULT_CURRENCY,
                reasons=[
                    "Operational interruption impact is unavailable because days of cover "
                    "and risk hours remaining are missing."
                ],
            )
        risk_hours_remaining = max(Decimal("0"), inputs.days_of_cover * Decimal("24"))
    else:
        risk_hours_remaining = max(Decimal("0"), inputs.risk_hours_remaining)

    if config is None:
        return unavailable_result(
            material_exposure_value=inputs.material_exposure_value,
            status="insufficient_config",
            currency=DEFAULT_CURRENCY,
            missing_config_fields=REQUIRED_CONFIG_FIELDS,
            reasons=[
                (
                    "Material Exposure Value is available from the existing material-based "
                    "calculation."
                ),
                (
                    "Operational interruption impact is unavailable because production "
                    "interruption economics are not configured for this plant/material context."
                ),
            ],
        )

    missing = missing_fields(config)
    if missing:
        return unavailable_result(
            material_exposure_value=inputs.material_exposure_value,
            status="insufficient_config",
            currency=config.currency or DEFAULT_CURRENCY,
            missing_config_fields=missing,
            reasons=[
                "Operational interruption impact is unavailable because required production "
                "interruption config fields are missing."
            ],
        )

    supply_gap_hours, gap_source = supply_gap(inputs, risk_hours_remaining)
    raw_gap_hours = max(
        Decimal("0"),
        config.restart_time_hours - config.survivable_hours_without_material,
    )
    estimated_interruption_hours = quantize_decimal(
        max(supply_gap_hours, raw_gap_hours)
        * config.line_dependency_ratio
        * (Decimal("1") - config.substitution_factor)
    )
    gross_production_impact = quantize_decimal(
        config.production_rate_mt_per_hour
        * config.finished_goods_value_per_mt
        * estimated_interruption_hours
    )
    downtime_impact = quantize_decimal(config.downtime_cost_per_hour * estimated_interruption_hours)
    restart_impact = (
        quantize_decimal(config.restart_cost)
        if estimated_interruption_hours > Decimal("0")
        else Decimal("0.00")
    )
    base_operational_impact = gross_production_impact + downtime_impact + restart_impact
    gross_operational_impact = quantize_decimal(
        base_operational_impact * config.cascading_impact_factor
    )
    interruption_probability = probability_for(inputs, config)
    final_impact = quantize_decimal(gross_operational_impact * interruption_probability)

    return OperationalInterruptionImpact(
        material_exposure_value=quantize_optional(inputs.material_exposure_value),
        operational_interruption_impact=final_impact,
        calculation_status="calculated",
        currency=config.currency or DEFAULT_CURRENCY,
        estimated_interruption_hours=estimated_interruption_hours,
        interruption_probability=interruption_probability,
        gross_production_impact=gross_production_impact,
        downtime_impact=downtime_impact,
        restart_impact=restart_impact,
        cascading_impact_factor=quantize_decimal(config.cascading_impact_factor),
        gross_operational_impact=gross_operational_impact,
        final_estimated_impact=final_impact,
        missing_config_fields=[],
        formula_version=FORMULA_VERSION,
        reason_chain=[
            f"Risk hours remaining used: {quantize_decimal(risk_hours_remaining)}.",
            (
                f"Supply gap hours: {quantize_decimal(supply_gap_hours)} "
                f"({gap_source}); restart survivability gap hours: "
                f"{quantize_decimal(raw_gap_hours)}."
            ),
            (
                "Estimated interruption hours = max(supply gap, restart survivability gap) "
                "x line dependency ratio x substitution exposure."
            ),
            (
                "Gross production impact = production rate x finished goods value x "
                "estimated interruption hours."
            ),
            (
                "Gross operational impact adds downtime and restart impact, then applies "
                "cascading impact factor."
            ),
            (
                "Final estimated impact = gross operational impact x deterministic "
                "interruption probability."
            ),
        ],
    )


def supply_gap(
    inputs: ProductionInterruptionInputs, risk_hours_remaining: Decimal
) -> tuple[Decimal, str]:
    if inputs.projected_exhaustion_date and inputs.next_trusted_inbound_eta:
        delta = inputs.next_trusted_inbound_eta - inputs.projected_exhaustion_date
        return (
            max(Decimal("0"), Decimal(str(delta.total_seconds())) / Decimal("3600")),
            "observed_inbound_eta",
        )
    if risk_hours_remaining <= Decimal("72"):
        return max(Decimal("0"), Decimal("72") - risk_hours_remaining), "estimated_fallback"
    return Decimal("0"), "none"


def probability_for(
    inputs: ProductionInterruptionInputs,
    config: ProductionInterruptionImpactConfig,
) -> Decimal:
    if config.interruption_probability_override is not None:
        return quantize_probability(config.interruption_probability_override)

    probability = URGENCY_PROBABILITIES.get(inputs.urgency_band, Decimal("0.10"))
    if inputs.continuity_severity == "critical":
        probability += Decimal("0.10")
    elif inputs.continuity_severity == "high":
        probability += Decimal("0.05")
    if inputs.trusted_inbound_ratio is not None and inputs.trusted_inbound_ratio < Decimal("0.40"):
        probability += Decimal("0.10")
    if inputs.shipment_confidence_low:
        probability += Decimal("0.05")
    if inputs.freshness_status in {"stale", "critical"}:
        probability += Decimal("0.05")
    probability -= Decimal("0.15") * config.substitution_factor
    if config.line_dependency_ratio < Decimal("0.5"):
        probability -= Decimal("0.10")
    return quantize_probability(max(Decimal("0"), min(probability, Decimal("0.95"))))


def missing_fields(config: ProductionInterruptionImpactConfig) -> list[str]:
    return [field for field in REQUIRED_CONFIG_FIELDS if getattr(config, field) is None]


def unavailable_result(
    *,
    material_exposure_value: Decimal | None,
    status: str,
    currency: str,
    reasons: list[str],
    missing_config_fields: list[str] | None = None,
) -> OperationalInterruptionImpact:
    return OperationalInterruptionImpact(
        material_exposure_value=quantize_optional(material_exposure_value),
        operational_interruption_impact=None,
        calculation_status=status,
        currency=currency,
        missing_config_fields=missing_config_fields or [],
        formula_version=FORMULA_VERSION,
        reason_chain=reasons,
    )


def quantize_optional(value: Decimal | None) -> Decimal | None:
    return quantize_decimal(value) if value is not None else None


def quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def quantize_probability(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
