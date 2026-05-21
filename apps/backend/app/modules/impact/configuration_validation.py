from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    MaterialProcessDependency,
    PlantMaterialThreshold,
    ProcessProductDependency,
    ProductionInterruptionImpactConfig,
    ProductionLine,
    Shipment,
    ShipmentInboundTrustConfig,
    StockSnapshot,
)
from app.models.enums import ShipmentState

ACTIVE_SHIPMENT_STATES = {
    ShipmentState.PLANNED,
    ShipmentState.IN_TRANSIT,
    ShipmentState.AT_PORT,
    ShipmentState.DISCHARGING,
    ShipmentState.INLAND_TRANSIT,
    ShipmentState.DELAYED,
}


class ConfigurationValidationFinding(BaseModel):
    finding_code: str
    severity: str
    area: str
    title: str
    description: str
    operational_impact: str
    suggested_fix: str
    affects_risk_precision: bool


class ConfigurationValidationResult(BaseModel):
    plant_id: int
    material_id: int
    validation_status: str
    readiness_score: Decimal
    findings: list[ConfigurationValidationFinding]
    blocking_errors_count: int
    warnings_count: int
    info_count: int
    reason_chain: list[str]


def validate_operational_configuration(
    db: Session,
    *,
    tenant_id: int,
    plant_id: int,
    material_id: int,
    now: datetime | None = None,
) -> ConfigurationValidationResult:
    evaluated_at = now or datetime.now(UTC)
    findings: list[ConfigurationValidationFinding] = []

    threshold = db.scalar(
        select(PlantMaterialThreshold).where(
            PlantMaterialThreshold.tenant_id == tenant_id,
            PlantMaterialThreshold.plant_id == plant_id,
            PlantMaterialThreshold.material_id == material_id,
        )
    )
    interruption_config = db.scalar(
        select(ProductionInterruptionImpactConfig).where(
            ProductionInterruptionImpactConfig.tenant_id == tenant_id,
            ProductionInterruptionImpactConfig.plant_id == plant_id,
            ProductionInterruptionImpactConfig.material_id == material_id,
            ProductionInterruptionImpactConfig.is_active.is_(True),
        )
    )
    material_dependencies = list(
        db.scalars(
            select(MaterialProcessDependency).where(
                MaterialProcessDependency.tenant_id == tenant_id,
                MaterialProcessDependency.material_id == material_id,
                MaterialProcessDependency.is_active.is_(True),
            )
        )
    )
    product_rows_by_process = product_mix_by_process(
        db,
        tenant_id=tenant_id,
        process_ids=[row.process_id for row in material_dependencies],
    )
    shipment_trust = db.scalar(
        select(ShipmentInboundTrustConfig).where(
            ShipmentInboundTrustConfig.tenant_id == tenant_id,
            ShipmentInboundTrustConfig.plant_id == plant_id,
            ShipmentInboundTrustConfig.material_id == material_id,
            ShipmentInboundTrustConfig.is_active.is_(True),
        )
    )
    active_shipments = list(
        db.scalars(
            select(Shipment).where(
                Shipment.tenant_id == tenant_id,
                Shipment.plant_id == plant_id,
                Shipment.material_id == material_id,
                Shipment.current_state.in_(ACTIVE_SHIPMENT_STATES),
            )
        )
    )
    latest_stock = db.scalar(
        select(StockSnapshot)
        .where(
            StockSnapshot.tenant_id == tenant_id,
            StockSnapshot.plant_id == plant_id,
            StockSnapshot.material_id == material_id,
        )
        .order_by(StockSnapshot.snapshot_time.desc())
        .limit(1)
    )
    meaningful_dependency = has_meaningful_dependency(
        interruption_config,
        material_dependencies,
    )

    validate_thresholds(findings, threshold, meaningful_dependency)
    validate_interruption_impact(
        findings,
        interruption_config,
        material_dependencies,
        has_product_process_dependency=any(product_rows_by_process.values()),
    )
    validate_product_process_dependency(
        findings,
        material_dependencies,
        product_rows_by_process,
        meaningful_dependency=meaningful_dependency,
    )
    validate_shipment_trust(findings, shipment_trust, active_shipments)
    validate_supplier_context(findings, db, tenant_id, plant_id, material_id, active_shipments)
    validate_inventory_visibility(findings, latest_stock, evaluated_at)
    validate_shipment_visibility(findings, active_shipments, shipment_trust)

    errors = sum(1 for item in findings if item.severity == "error")
    warnings = sum(1 for item in findings if item.severity == "warning")
    info = sum(1 for item in findings if item.severity == "info")
    score = clamp_score(Decimal("100") - Decimal(errors * 25 + warnings * 8 + info * 2))
    status = validation_status(score, errors)
    return ConfigurationValidationResult(
        plant_id=plant_id,
        material_id=material_id,
        validation_status=status,
        readiness_score=score,
        findings=sorted(findings, key=finding_sort_key),
        blocking_errors_count=errors,
        warnings_count=warnings,
        info_count=info,
        reason_chain=[
            f"Configuration validation found {errors} errors, {warnings} warnings, and {info} informational findings.",
            f"Readiness score is {score}, mapped to {status}.",
        ],
    )


def validate_thresholds(
    findings: list[ConfigurationValidationFinding],
    threshold: PlantMaterialThreshold | None,
    meaningful_dependency: bool,
) -> None:
    if threshold is None:
        findings.append(
            finding(
                "missing_continuity_thresholds",
                "warning",
                "continuity_thresholds",
                "Continuity thresholds missing",
                "No warning or critical days-of-cover thresholds are configured for this plant-material context.",
                "OpsDeck will use fallback continuity thresholds, reducing plant-specific precision.",
                "Configure warning and critical timing under Continuity Thresholds.",
            )
        )
        return
    if threshold.warning_days < threshold.threshold_days:
        findings.append(
            finding(
                "warning_days_less_than_threshold_days",
                "error",
                "continuity_thresholds",
                "Warning threshold is below critical threshold",
                "warning_days is lower than threshold_days.",
                "A material could become critical before it becomes a warning, which makes risk escalation contradictory.",
                "Set warning_days greater than or equal to the critical threshold.",
            )
        )
    if meaningful_dependency and threshold.threshold_days == 0:
        findings.append(
            finding(
                "zero_critical_threshold_with_dependency",
                "warning",
                "continuity_thresholds",
                "Critical threshold is zero for a dependent material",
                "This material has operational dependency, but the critical threshold is configured as 0 days.",
                "OpsDeck may wait until cover is exhausted before treating the material as critical.",
                "Use a positive critical threshold for materials that can disrupt production.",
            )
        )
    if threshold.warning_days > (threshold.threshold_days * Decimal("4")) and threshold.warning_days > 30:
        findings.append(
            finding(
                "warning_threshold_unusually_high",
                "warning",
                "continuity_thresholds",
                "Warning threshold is unusually far from critical",
                "warning_days is much higher than the critical threshold.",
                "OpsDeck may keep this material in warning state for a long time, which can dilute operational attention.",
                "Confirm this is a strategic or import-sensitive material, or reduce warning_days.",
            )
        )
    if threshold.stockout_alert_horizon_days is None:
        findings.append(
            finding(
                "stockout_alert_horizon_missing",
                "info",
                "continuity_thresholds",
                "Projected stockout alert horizon missing",
                "No custom projected stockout alert horizon is configured.",
                "OpsDeck will use the fallback projected stockout window.",
                "Set stockout_alert_horizon_days if this material needs a custom escalation window.",
                affects_precision=False,
            )
        )


def validate_interruption_impact(
    findings: list[ConfigurationValidationFinding],
    config: ProductionInterruptionImpactConfig | None,
    material_dependencies: list[MaterialProcessDependency],
    *,
    has_product_process_dependency: bool,
) -> None:
    if config is None:
        findings.append(
            finding(
                "missing_interruption_impact_config",
                "warning",
                "interruption_impact",
                "Interruption impact assumptions missing",
                "No active production interruption impact config exists for this plant-material context.",
                "Operational interruption impact will be unavailable or fall back to material exposure only.",
                "Configure Risk Value / Interruption Impact assumptions.",
            )
        )
        return
    if config.line_dependency_ratio > 0 and config.production_rate_mt_per_hour == 0:
        findings.append(
            finding(
                "zero_production_rate_with_dependency",
                "warning",
                "interruption_impact",
                "Production rate is zero for a dependent material",
                "line_dependency_ratio is above zero, but production_rate_mt_per_hour is 0.",
                "Production impact may be understated even when continuity risk is real.",
                "Enter the affected output rate or set dependency to no meaningful production impact.",
            )
        )
    if (
        config.line_dependency_ratio > 0
        and config.finished_goods_value_per_mt == 0
        and not has_product_process_dependency
    ):
        findings.append(
            finding(
                "zero_output_value_without_product_mix",
                "warning",
                "interruption_impact",
                "Output value is zero without product mix",
                "finished_goods_value_per_mt is 0 and no product/process product mix is configured.",
                "Operational interruption impact may be materially understated.",
                "Enter weighted output value per MT or configure Product & Process Dependency.",
            )
        )
    if config.line_dependency_ratio == 0 and material_dependencies:
        findings.append(
            finding(
                "zero_line_dependency_with_process_dependency",
                "warning",
                "interruption_impact",
                "Interruption config conflicts with process dependency",
                "line_dependency_ratio is 0, but material-process dependency rows exist.",
                "OpsDeck may treat the material as operationally non-dependent while process dependency suggests otherwise.",
                "Align the dependency choice with Product & Process Dependency configuration.",
            )
        )
    if config.restart_cost == 0 and config.restart_time_hours == 0:
        findings.append(
            finding(
                "restart_assumption_zero",
                "info",
                "interruption_impact",
                "Restart assumptions are zero",
                "restart_cost and restart_time_hours are both configured as 0.",
                "This may be correct if restart has no meaningful stabilization cost.",
                "Confirm restart cost/time are intentionally zero.",
                affects_precision=False,
            )
        )
    if config.interruption_probability_override is not None:
        findings.append(
            finding(
                "probability_override_configured",
                "info",
                "interruption_impact",
                "Probability override is configured",
                "A manual interruption probability override is active.",
                "OpsDeck will use this override instead of calculating probability from risk severity, inbound trust, freshness, and dependency.",
                "Leave the override blank if OpsDeck should calculate probability automatically.",
            )
        )


def validate_product_process_dependency(
    findings: list[ConfigurationValidationFinding],
    material_dependencies: list[MaterialProcessDependency],
    product_rows_by_process: dict[int, list[ProcessProductDependency]],
    *,
    meaningful_dependency: bool,
) -> None:
    if meaningful_dependency and not material_dependencies:
        findings.append(
            finding(
                "missing_material_process_dependency",
                "warning",
                "product_process_dependency",
                "Material-process dependency missing",
                "The material appears operationally dependent, but no material-process dependency is configured.",
                "Interruption impact may use blended fallback economics instead of process/product-level exposure.",
                "Add material dependency rows under Product & Process Dependency.",
            )
        )
    for dependency in material_dependencies:
        if dependency.dependency_ratio < 0 or dependency.dependency_ratio > 1:
            findings.append(
                finding(
                    "dependency_ratio_out_of_range",
                    "error",
                    "product_process_dependency",
                    "Dependency ratio is outside 0-1",
                    "A material-process dependency ratio is outside the allowed range.",
                    "Process exposure weighting becomes invalid.",
                    "Update dependency_ratio to a value from 0.0 to 1.0.",
                )
            )
        rows = product_rows_by_process.get(dependency.process_id, [])
        if not rows:
            findings.append(
                finding(
                    "process_product_mix_missing",
                    "warning",
                    "product_process_dependency",
                    "Product mix missing for affected process",
                    "This material is linked to a process, but that process has no product mix configured.",
                    "Interruption impact may fall back to blended output value or lose product-level precision.",
                    "Add product mix rows under Product & Process Dependency.",
                )
            )
            continue
        total_share = sum((row.output_share_ratio for row in rows), Decimal("0"))
        if total_share > Decimal("1.20"):
            findings.append(
                finding(
                    "product_mix_share_total_high",
                    "warning",
                    "product_process_dependency",
                    "Product mix share is above 120%",
                    "The configured product mix output shares for a process total more than 120%.",
                    "Product-level exposure may be overstated.",
                    "Review output share percentages for the process.",
                )
            )
        if total_share < Decimal("0.50"):
            findings.append(
                finding(
                    "product_mix_share_total_low",
                    "warning",
                    "product_process_dependency",
                    "Product mix share is below 50%",
                    "The configured product mix output shares for a process total less than 50%.",
                    "Product-level exposure may be understated.",
                    "Add missing product mix rows or adjust output shares.",
                )
            )
        for row in rows:
            if row.output_share_ratio < 0 or row.output_share_ratio > 1:
                findings.append(
                    finding(
                        "output_share_ratio_out_of_range",
                        "error",
                        "product_process_dependency",
                        "Output share is outside 0-1",
                        "A product mix output_share_ratio is outside the allowed range.",
                        "Product exposure weighting becomes invalid.",
                        "Update output_share_ratio to a value from 0.0 to 1.0.",
                    )
                )
            if row.operational_criticality_factor < 0 or row.operational_criticality_factor > 2:
                findings.append(
                    finding(
                        "criticality_factor_out_of_range",
                        "error",
                        "product_process_dependency",
                        "Operational criticality is outside 0-2",
                        "A product mix operational_criticality_factor is outside the allowed range.",
                        "Operational exposure weighting becomes invalid.",
                        "Update operational_criticality_factor to a value from 0.0 to 2.0.",
                    )
                )
            if row.product_value_per_mt == 0:
                findings.append(
                    finding(
                        "product_value_zero",
                        "warning",
                        "product_process_dependency",
                        "Product value per MT is zero",
                        "A configured product mix row has product_value_per_mt set to 0.",
                        "Product-level interruption exposure may be understated.",
                        "Enter a realistic product value per MT for the product row.",
                    )
                )


def validate_shipment_trust(
    findings: list[ConfigurationValidationFinding],
    config: ShipmentInboundTrustConfig | None,
    active_shipments: list[Shipment],
) -> None:
    if config is None:
        if active_shipments:
            findings.append(
                finding(
                    "missing_shipment_inbound_trust_config",
                    "warning",
                    "shipment_inbound_trust",
                    "Shipment trust calibration missing",
                    "Active inbound shipments exist, but no shipment inbound trust config is configured.",
                    "OpsDeck will use deterministic default visibility cadence and ETA tolerance.",
                    "Configure Shipment & Inbound Trust for this plant-material context.",
                )
            )
        return
    if config.visibility_profile in {"ocean", "port"} and config.expected_visibility_cadence_hours < 12:
        findings.append(
            finding(
                "import_profile_cadence_too_strict",
                "warning",
                "shipment_inbound_trust",
                "Import visibility cadence may be too strict",
                "Ocean or port visibility is configured with expected cadence below 12 hours.",
                "Normal import update gaps may be treated as weak visibility.",
                "Use a cadence that reflects normal ocean or port update rhythm.",
            )
        )
    if config.visibility_profile == "inland" and config.expected_visibility_cadence_hours > 48:
        findings.append(
            finding(
                "inland_cadence_too_loose",
                "warning",
                "shipment_inbound_trust",
                "Inland visibility cadence may be too loose",
                "Inland movement is configured with expected cadence above 48 hours.",
                "Late truck or near-plant movement issues may be detected too slowly.",
                "Use a shorter cadence for inland movement.",
            )
        )
    if config.eta_drift_tolerance_hours == 0:
        findings.append(
            finding(
                "eta_drift_tolerance_zero",
                "warning",
                "shipment_inbound_trust",
                "ETA drift tolerance is zero",
                "Any ETA movement will reduce confidence.",
                "OpsDeck may overreact to normal ETA changes.",
                "Set a small positive ETA drift tolerance.",
            )
        )
    if config.weak_visibility_threshold < Decimal("0.25"):
        findings.append(
            finding(
                "weak_visibility_threshold_low",
                "warning",
                "shipment_inbound_trust",
                "Weak visibility threshold is very tolerant",
                "Inbound protection is only considered weak below a very low visibility confidence.",
                "OpsDeck may understate uncertainty in inbound protection.",
                "Use a threshold of at least 0.25 unless this material is intentionally tolerant.",
            )
        )
    if config.weak_visibility_threshold > Decimal("0.90"):
        findings.append(
            finding(
                "weak_visibility_threshold_high",
                "warning",
                "shipment_inbound_trust",
                "Weak visibility threshold is very strict",
                "Inbound protection is considered weak unless visibility confidence is above 0.90.",
                "OpsDeck may overstate uncertainty for normal shipments.",
                "Use a lower threshold unless this material needs unusually strict visibility.",
            )
        )
    if config.minimum_trusted_inbound_ratio is None:
        findings.append(
            finding(
                "minimum_trusted_inbound_ratio_missing",
                "info",
                "shipment_inbound_trust",
                "Minimum trusted inbound ratio missing",
                "No minimum trusted inbound ratio is configured.",
                "OpsDeck will only use the weak visibility threshold to judge inbound protection strength.",
                "Set a minimum trusted inbound ratio if this material requires a minimum verified protection level.",
                affects_precision=False,
            )
        )


def validate_supplier_context(
    findings: list[ConfigurationValidationFinding],
    db: Session,
    tenant_id: int,
    plant_id: int,
    material_id: int,
    active_shipments: list[Shipment],
) -> None:
    sample_size = db.scalar(
        select(func.count(Shipment.id)).where(
            Shipment.tenant_id == tenant_id,
            Shipment.plant_id == plant_id,
            Shipment.material_id == material_id,
            Shipment.supplier_id.is_not(None),
        )
    ) or 0
    if sample_size and sample_size < 3:
        findings.append(
            finding(
                "supplier_context_sample_low",
                "warning",
                "supplier_context",
                "Supplier-context history is thin",
                f"Only {sample_size} supplier-linked shipment sample is available for this plant-material context.",
                "Supplier reliability may use a low-confidence or neutral fallback.",
                "Allow more supplier-linked shipment history to accumulate.",
            )
        )
        findings.append(
            finding(
                "supplier_reliability_neutral_fallback",
                "info",
                "supplier_context",
                "Supplier reliability fallback may be neutral",
                "Supplier-context evidence is below the preferred sample size.",
                "Supplier reliability will be less context-specific until more history is available.",
                "Review supplier linkage on inbound shipments and continue collecting shipment history.",
            )
        )
    for shipment in active_shipments:
        if shipment.supplier_id is None and not shipment.supplier_name:
            findings.append(
                finding(
                    "active_shipment_supplier_missing",
                    "warning",
                    "supplier_context",
                    "Active inbound shipment is missing supplier context",
                    f"Shipment {shipment.shipment_id} has no supplier identity.",
                    "Supplier reliability context cannot be assessed for this inbound signal.",
                    "Link or provide supplier identity for the shipment.",
                )
            )


def validate_inventory_visibility(
    findings: list[ConfigurationValidationFinding],
    stock: StockSnapshot | None,
    now: datetime,
) -> None:
    if stock is None:
        findings.append(
            finding(
                "stock_snapshot_missing",
                "warning",
                "inventory_visibility",
                "Inventory visibility missing",
                "No stock snapshot exists for this plant-material context.",
                "Days-of-cover and threshold validation cannot use current inventory visibility.",
                "Upload or sync an inventory snapshot for this material.",
            )
        )
        return
    if stock.daily_consumption_mt <= 0:
        findings.append(
            finding(
                "daily_consumption_non_positive",
                "error",
                "inventory_visibility",
                "Daily consumption is zero or negative",
                "daily_consumption_rate is not positive for a monitored material.",
                "Days-of-cover cannot be calculated reliably.",
                "Upload or configure a positive daily consumption rate.",
            )
        )
    if stock.available_to_consume_mt < 0:
        findings.append(
            finding(
                "usable_stock_negative",
                "error",
                "inventory_visibility",
                "Usable stock is negative",
                "available_to_consume_mt is below zero.",
                "Continuity cover calculations become invalid.",
                "Correct the inventory snapshot so usable stock is not negative.",
            )
        )
    snapshot_time = ensure_aware(stock.snapshot_time)
    current_time = ensure_aware(now)
    age_hours = Decimal(str(max(0.0, (current_time - snapshot_time).total_seconds() / 3600)))
    if age_hours > Decimal("168"):
        findings.append(
            finding(
                "stock_snapshot_critical_freshness",
                "warning",
                "inventory_visibility",
                "Stock snapshot is critically stale",
                "The latest inventory snapshot is more than 7 days old.",
                "Continuity cover may not reflect current operations.",
                "Refresh inventory visibility for this material.",
            )
        )
    elif age_hours > Decimal("48"):
        findings.append(
            finding(
                "stock_snapshot_stale",
                "warning",
                "inventory_visibility",
                "Stock snapshot is stale",
                "The latest inventory snapshot is more than 48 hours old.",
                "Continuity cover precision is reduced.",
                "Refresh inventory visibility for this material.",
            )
        )
    if (
        stock.on_hand_mt - stock.available_to_consume_mt > Decimal("0")
        and stock.quality_held_mt == 0
    ):
        findings.append(
            finding(
                "blocked_stock_reason_missing",
                "warning",
                "inventory_visibility",
                "Unavailable stock is not explained by quality hold",
                "Available-to-consume stock is materially below on-hand stock, but quality hold is zero.",
                "Blocked or reserved stock may be missing from the source data.",
                "Confirm whether blocked/reserved quantities are included in uploaded inventory data.",
            )
        )


def validate_shipment_visibility(
    findings: list[ConfigurationValidationFinding],
    active_shipments: list[Shipment],
    trust_config: ShipmentInboundTrustConfig | None,
) -> None:
    profile = trust_config.visibility_profile if trust_config is not None else None
    for shipment in active_shipments:
        if shipment.current_eta is None:
            findings.append(
                finding(
                    "active_shipment_eta_missing",
                    "warning",
                    "shipment_visibility",
                    "Active inbound shipment is missing ETA",
                    f"Shipment {shipment.shipment_id} has no current ETA.",
                    "Inbound cover timing cannot be trusted for this shipment.",
                    "Add or refresh the current ETA for the shipment.",
                )
            )
        if shipment.last_tracking_update_at is None and shipment.latest_update_at is None:
            findings.append(
                finding(
                    "active_shipment_update_missing",
                    "warning",
                    "shipment_visibility",
                    "Active inbound shipment is missing update timestamp",
                    f"Shipment {shipment.shipment_id} has no latest update or tracking timestamp.",
                    "Visibility confidence may fall back to conservative assumptions.",
                    "Provide a latest update timestamp or tracking update.",
                )
            )
        if shipment.plant_id is None or shipment.material_id is None:
            findings.append(
                finding(
                    "active_shipment_context_missing",
                    "warning",
                    "shipment_visibility",
                    "Active inbound shipment is missing plant/material linkage",
                    f"Shipment {shipment.shipment_id} is not linked to both plant and material.",
                    "Inbound protection cannot be attributed to the selected plant-material context.",
                    "Link the shipment to the correct plant and material.",
                )
            )
        if shipment.quantity_mt <= 0:
            findings.append(
                finding(
                    "active_shipment_quantity_non_positive",
                    "warning",
                    "shipment_visibility",
                    "Active inbound shipment quantity is not positive",
                    f"Shipment {shipment.shipment_id} has physical inbound quantity at or below zero.",
                    "Inbound protection may be ignored or understated.",
                    "Correct the physical inbound quantity.",
                )
            )
        if profile in {"ocean", "port"} and not (
            shipment.vessel_name or shipment.imo_number or shipment.mmsi
        ):
            findings.append(
                finding(
                    "ocean_shipment_vessel_identifier_missing",
                    "info",
                    "shipment_visibility",
                    "Vessel identifiers missing for import profile",
                    f"Shipment {shipment.shipment_id} is evaluated under import-style visibility, but vessel identifiers are missing.",
                    "Ocean shipment visibility may have less explainability.",
                    "Add vessel name, IMO, or MMSI when available.",
                    affects_precision=False,
                )
            )


def product_mix_by_process(
    db: Session,
    *,
    tenant_id: int,
    process_ids: list[int],
) -> dict[int, list[ProcessProductDependency]]:
    if not process_ids:
        return {}
    active_process_ids = set(
        db.scalars(
            select(ProductionLine.id).where(
                ProductionLine.tenant_id == tenant_id,
                ProductionLine.id.in_(process_ids),
                ProductionLine.is_active.is_(True),
            )
        )
    )
    rows = db.scalars(
        select(ProcessProductDependency).where(
            ProcessProductDependency.tenant_id == tenant_id,
            ProcessProductDependency.process_id.in_(active_process_ids),
            ProcessProductDependency.is_active.is_(True),
        )
    ).all()
    grouped: dict[int, list[ProcessProductDependency]] = {
        process_id: [] for process_id in active_process_ids
    }
    for row in rows:
        grouped.setdefault(row.process_id, []).append(row)
    return grouped


def has_meaningful_dependency(
    config: ProductionInterruptionImpactConfig | None,
    material_dependencies: list[MaterialProcessDependency],
) -> bool:
    if config is not None and config.line_dependency_ratio > 0:
        return True
    return any(row.dependency_ratio > 0 for row in material_dependencies)


def finding(
    finding_code: str,
    severity: str,
    area: str,
    title: str,
    description: str,
    operational_impact: str,
    suggested_fix: str,
    *,
    affects_precision: bool = True,
) -> ConfigurationValidationFinding:
    return ConfigurationValidationFinding(
        finding_code=finding_code,
        severity=severity,
        area=area,
        title=title,
        description=description,
        operational_impact=operational_impact,
        suggested_fix=suggested_fix,
        affects_risk_precision=affects_precision,
    )


def validation_status(score: Decimal, errors: int) -> str:
    if errors:
        return "invalid"
    if score < Decimal("50"):
        return "incomplete"
    if score < Decimal("85"):
        return "usable_with_warnings"
    return "ready"


def clamp_score(value: Decimal) -> Decimal:
    return max(Decimal("0.00"), min(Decimal("100.00"), value.quantize(Decimal("0.01"))))


def finding_sort_key(item: ConfigurationValidationFinding) -> tuple[int, str, str]:
    severity_rank = {"error": 0, "warning": 1, "info": 2}
    return severity_rank.get(item.severity, 9), item.area, item.finding_code


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
