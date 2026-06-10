from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    MaterialProcessDependency,
    ProcessProductDependency,
    ProductionInterruptionImpactConfig,
    ProductionLine,
)
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


@dataclass(frozen=True)
class ProcessExposureLine:
    process_id: int
    process_name: str
    dependency_ratio: Decimal
    effective_dependency_ratio: Decimal
    substitution_factor: Decimal
    survivability_hours: Decimal
    weighted_process_output_value: Decimal
    process_production_impact: Decimal
    products: tuple[str, ...]


@dataclass(frozen=True)
class DependencyExposureResult:
    weighted_output_value_per_mt: Decimal
    gross_production_impact: Decimal
    process_lines: tuple[ProcessExposureLine, ...]


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

    generic_config = db.scalar(
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
    if generic_config is not None:
        return generic_config

    return db.scalar(
        select(ProductionInterruptionImpactConfig)
        .where(
            ProductionInterruptionImpactConfig.tenant_id == tenant_id,
            ProductionInterruptionImpactConfig.plant_id == plant_id,
            ProductionInterruptionImpactConfig.material_id == material_id,
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
    db: Session | None = None,
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
    base_gap_hours = max(supply_gap_hours, raw_gap_hours)
    dependency_exposure = dependency_exposure_for(
        db,
        inputs=inputs,
        config=config,
        base_gap_hours=base_gap_hours,
    )
    estimated_interruption_hours = quantize_decimal(
        base_gap_hours * config.line_dependency_ratio * (Decimal("1") - config.substitution_factor)
    )
    gross_production_impact = dependency_exposure.gross_production_impact
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
            *dependency_exposure_reasons(dependency_exposure, config),
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


def dependency_exposure_for(
    db: Session | None,
    *,
    inputs: ProductionInterruptionInputs,
    config: ProductionInterruptionImpactConfig,
    base_gap_hours: Decimal,
) -> DependencyExposureResult:
    fallback_interruption_hours = quantize_decimal(
        base_gap_hours * config.line_dependency_ratio * (Decimal("1") - config.substitution_factor)
    )
    fallback_gross_production_impact = quantize_decimal(
        config.production_rate_mt_per_hour
        * config.finished_goods_value_per_mt
        * fallback_interruption_hours
    )
    fallback = DependencyExposureResult(
        weighted_output_value_per_mt=quantize_decimal(config.finished_goods_value_per_mt),
        gross_production_impact=fallback_gross_production_impact,
        process_lines=(),
    )
    if db is None:
        return fallback

    dependencies = latest_material_process_dependencies(
        db.scalars(
            select(MaterialProcessDependency)
            .where(
                MaterialProcessDependency.tenant_id == inputs.tenant_id,
                MaterialProcessDependency.material_id == inputs.material_id,
                MaterialProcessDependency.is_active.is_(True),
            )
            .order_by(
                MaterialProcessDependency.updated_at,
                MaterialProcessDependency.id,
            )
        )
    )
    if not dependencies:
        return fallback

    lines: list[ProcessExposureLine] = []
    gross_production_impact = Decimal("0")
    weighted_output_total = Decimal("0")
    for dependency in dependencies:
        process = db.scalar(
            select(ProductionLine).where(
                ProductionLine.tenant_id == inputs.tenant_id,
                ProductionLine.id == dependency.process_id,
                ProductionLine.plant_id == inputs.plant_id,
                ProductionLine.is_active.is_(True),
            )
        )
        if process is None:
            continue
        products = latest_process_products(
            db.scalars(
                select(ProcessProductDependency)
                .where(
                    ProcessProductDependency.tenant_id == inputs.tenant_id,
                    ProcessProductDependency.process_id == process.id,
                    ProcessProductDependency.is_active.is_(True),
                )
                .order_by(
                    ProcessProductDependency.updated_at,
                    ProcessProductDependency.id,
                )
            )
        )
        if not products:
            continue
        weighted_process_output_value = quantize_decimal(
            sum(
                (
                    safe_ratio(product.output_share_ratio)
                    * product.product_value_per_mt
                    * safe_criticality(product.operational_criticality_factor)
                    for product in products
                ),
                start=Decimal("0"),
            )
        )
        dependency_ratio = safe_ratio(dependency.dependency_ratio)
        substitution_factor = safe_ratio(
            dependency.substitution_factor
            if dependency.substitution_factor is not None
            else config.substitution_factor
        )
        survivability_hours = (
            max(Decimal("0"), dependency.survivability_hours)
            if dependency.survivability_hours is not None
            else config.survivable_hours_without_material
        )
        process_gap_hours = max(
            base_gap_hours,
            max(Decimal("0"), config.restart_time_hours - survivability_hours),
        )
        effective_dependency = quantize_probability(
            dependency_ratio * config.line_dependency_ratio * (Decimal("1") - substitution_factor)
        )
        process_interruption_hours = quantize_decimal(process_gap_hours * effective_dependency)
        process_impact = quantize_decimal(
            config.production_rate_mt_per_hour
            * weighted_process_output_value
            * process_interruption_hours
        )
        gross_production_impact += process_impact
        weighted_output_total += weighted_process_output_value * dependency_ratio
        lines.append(
            ProcessExposureLine(
                process_id=process.id,
                process_name=process.name,
                dependency_ratio=quantize_probability(dependency_ratio),
                effective_dependency_ratio=effective_dependency,
                substitution_factor=quantize_probability(substitution_factor),
                survivability_hours=quantize_decimal(survivability_hours),
                weighted_process_output_value=weighted_process_output_value,
                process_production_impact=process_impact,
                products=tuple(
                    (
                        f"{product.product_name} "
                        f"{quantize_probability(safe_ratio(product.output_share_ratio))} share "
                        f"x {quantize_decimal(product.product_value_per_mt)} per MT "
                        "x criticality "
                        f"{quantize_probability(safe_criticality(product.operational_criticality_factor))}"
                    )
                    for product in products
                ),
            )
        )
    if not lines:
        return fallback
    return DependencyExposureResult(
        weighted_output_value_per_mt=quantize_decimal(weighted_output_total),
        gross_production_impact=quantize_decimal(gross_production_impact),
        process_lines=tuple(lines),
    )


def latest_material_process_dependencies(
    rows: Iterable[MaterialProcessDependency],
) -> list[MaterialProcessDependency]:
    by_process: dict[int, MaterialProcessDependency] = {}
    for row in rows:
        by_process[row.process_id] = row
    return list(by_process.values())


def latest_process_products(
    rows: Iterable[ProcessProductDependency],
) -> list[ProcessProductDependency]:
    by_product: dict[str, ProcessProductDependency] = {}
    for row in rows:
        by_product[row.product_name.strip().lower()] = row
    return list(by_product.values())


def dependency_exposure_reasons(
    exposure: DependencyExposureResult,
    config: ProductionInterruptionImpactConfig,
) -> list[str]:
    if not exposure.process_lines:
        return [
            (
                "No active material-process-product dependency data was available; "
                "fallback weighted output value per MT "
                f"{quantize_decimal(config.finished_goods_value_per_mt)} "
                "was used."
            )
        ]
    reasons = [
        (
            "Product and process dependency model used weighted process/product exposure "
            f"value per MT {exposure.weighted_output_value_per_mt}."
        )
    ]
    for line in exposure.process_lines:
        reasons.append(
            (
                f"Material affects {line.process_name} operations with dependency ratio "
                f"{line.dependency_ratio}; effective process dependency after line/substitution "
                f"weighting is {line.effective_dependency_ratio}."
            )
        )
        reasons.append(
            (
                f"{line.process_name} weighted product exposure value is "
                f"{line.weighted_process_output_value} per MT; production impact contribution "
                f"is {line.process_production_impact}."
            )
        )
        reasons.append(f"{line.process_name} output mix: {'; '.join(line.products)}.")
    return reasons


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


def safe_ratio(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(value, Decimal("1")))


def safe_criticality(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(value, Decimal("2")))


def quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def quantize_probability(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
