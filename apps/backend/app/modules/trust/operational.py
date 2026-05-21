from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Material,
    MaterialProcessDependency,
    Plant,
    PlantMaterialThreshold,
    ProcessProductDependency,
    ProductionInterruptionImpactConfig,
    Shipment,
    ShipmentInboundTrustConfig,
)
from app.models.enums import ShipmentState
from app.modules.stock.schemas import InventoryContinuityResult

AREA_WEIGHTS = {
    "continuity_thresholds": Decimal("20"),
    "interruption_impact": Decimal("20"),
    "product_process_dependency": Decimal("20"),
    "shipment_inbound_trust": Decimal("15"),
    "supplier_context": Decimal("10"),
    "inventory_visibility": Decimal("10"),
    "shipment_visibility": Decimal("5"),
}

ACTIVE_SHIPMENT_STATES = {
    ShipmentState.PLANNED,
    ShipmentState.IN_TRANSIT,
    ShipmentState.AT_PORT,
    ShipmentState.DISCHARGING,
    ShipmentState.INLAND_TRANSIT,
    ShipmentState.DELAYED,
}


class ConfigurationCompletenessResult(BaseModel):
    overall_completeness_score: Decimal
    operational_confidence_band: str
    completeness_by_area: dict[str, Decimal]
    missing_assumptions: list[str]
    degraded_reasoning_areas: list[str]
    confidence_reason_chain: list[str]


class RiskOperationalTrustResult(BaseModel):
    risk_precision_band: str
    reasoning_strength: str
    trusted_signal_count: int
    weak_signal_count: int
    missing_signal_count: int
    trust_penalties: list[str]
    trust_boosts: list[str]
    operational_trust_score: Decimal


def evaluate_configuration_completeness(
    db: Session,
    *,
    tenant_id: int,
    plant_id: int,
    material_id: int,
    inventory: InventoryContinuityResult | None = None,
) -> ConfigurationCompletenessResult:
    area_scores: dict[str, Decimal] = {}
    missing: list[str] = []
    degraded: list[str] = []
    reasons: list[str] = []

    threshold = db.scalar(
        select(PlantMaterialThreshold).where(
            PlantMaterialThreshold.tenant_id == tenant_id,
            PlantMaterialThreshold.plant_id == plant_id,
            PlantMaterialThreshold.material_id == material_id,
        )
    )
    score_area(
        "continuity_thresholds",
        threshold is not None,
        area_scores,
        missing,
        reasons,
        configured_text="Continuity thresholds configured for this plant-material context.",
        missing_text="Continuity thresholds are not configured.",
    )

    interruption_config = db.scalar(
        select(ProductionInterruptionImpactConfig).where(
            ProductionInterruptionImpactConfig.tenant_id == tenant_id,
            ProductionInterruptionImpactConfig.plant_id == plant_id,
            ProductionInterruptionImpactConfig.material_id == material_id,
            ProductionInterruptionImpactConfig.is_active.is_(True),
        )
    )
    score_area(
        "interruption_impact",
        interruption_config is not None,
        area_scores,
        missing,
        reasons,
        configured_text="Interruption impact assumptions are configured.",
        missing_text="Interruption impact assumptions are not configured.",
    )

    process_dependency_score = product_process_dependency_score(
        db,
        tenant_id=tenant_id,
        material_id=material_id,
    )
    area_scores["product_process_dependency"] = process_dependency_score
    if process_dependency_score == Decimal("1.00"):
        reasons.append("Product/process dependency is configured.")
    elif process_dependency_score > 0:
        degraded.append("product_process_dependency")
        reasons.append(
            "Product/process dependency is partially configured; process or product mix is incomplete."
        )
    else:
        missing.append("Product/process dependency is not configured.")
        reasons.append(
            "Interruption impact uses fallback weighted output value because no process dependency is configured."
        )

    shipment_trust = db.scalar(
        select(ShipmentInboundTrustConfig).where(
            ShipmentInboundTrustConfig.tenant_id == tenant_id,
            ShipmentInboundTrustConfig.plant_id == plant_id,
            ShipmentInboundTrustConfig.material_id == material_id,
            ShipmentInboundTrustConfig.is_active.is_(True),
        )
    )
    score_area(
        "shipment_inbound_trust",
        shipment_trust is not None,
        area_scores,
        missing,
        reasons,
        configured_text="Shipment trust calibration exists for this plant-material context.",
        missing_text="Shipment trust calibration is missing.",
    )

    supplier_score, supplier_reason = supplier_context_score(
        db,
        tenant_id=tenant_id,
        plant_id=plant_id,
        material_id=material_id,
    )
    area_scores["supplier_context"] = supplier_score
    reasons.append(supplier_reason)
    if supplier_score < Decimal("1.00"):
        degraded.append("supplier_context")

    inventory_score, inventory_reason = inventory_visibility_score(inventory)
    area_scores["inventory_visibility"] = inventory_score
    reasons.append(inventory_reason)
    if inventory_score == 0:
        missing.append("Inventory visibility is missing or insufficient.")
    elif inventory_score < Decimal("1.00"):
        degraded.append("inventory_visibility")

    shipment_score, shipment_reason = shipment_visibility_score(
        db,
        tenant_id=tenant_id,
        plant_id=plant_id,
        material_id=material_id,
    )
    area_scores["shipment_visibility"] = shipment_score
    reasons.append(shipment_reason)
    if shipment_score == 0:
        missing.append("Shipment visibility signals are missing.")
    elif shipment_score < Decimal("1.00"):
        degraded.append("shipment_visibility")

    total = sum(
        AREA_WEIGHTS[area] * area_scores.get(area, Decimal("0"))
        for area in AREA_WEIGHTS
    )
    total = quantize_score(total)
    band = confidence_band(total)
    reasons.append(f"Configuration completeness score is {total}, mapped to {band}.")
    return ConfigurationCompletenessResult(
        overall_completeness_score=total,
        operational_confidence_band=band,
        completeness_by_area={area: quantize_ratio(area_scores.get(area, Decimal("0"))) for area in AREA_WEIGHTS},
        missing_assumptions=missing,
        degraded_reasoning_areas=sorted(set(degraded)),
        confidence_reason_chain=reasons,
    )


def evaluate_risk_operational_trust(
    risk: Any,
    completeness: ConfigurationCompletenessResult,
    *,
    inventory: InventoryContinuityResult | None = None,
) -> RiskOperationalTrustResult:
    score = Decimal(completeness.overall_completeness_score)
    penalties = list(completeness.missing_assumptions)
    boosts: list[str] = []
    trusted = sum(1 for value in completeness.completeness_by_area.values() if value >= Decimal("0.85"))
    weak = sum(1 for value in completeness.completeness_by_area.values() if Decimal("0") < value < Decimal("0.85"))
    missing = sum(1 for value in completeness.completeness_by_area.values() if value == 0)

    impact = getattr(risk, "operational_interruption_impact", None)
    if impact is not None:
        if impact.calculation_status == "calculated":
            boosts.append("Interruption impact fully configured.")
            score += Decimal("5")
        elif impact.calculation_status == "insufficient_config":
            penalties.append("Fallback interruption economics in use; operational impact precision is reduced.")
            score -= Decimal("8")
        elif impact.calculation_status == "insufficient_data":
            penalties.append("Interruption impact has insufficient operational timing data.")
            score -= Decimal("6")

    if completeness.completeness_by_area.get("product_process_dependency") == Decimal("1.00"):
        boosts.append("Process dependency configured.")
    elif completeness.completeness_by_area.get("product_process_dependency") == Decimal("0.00"):
        penalties.append("No process dependency configured; fallback weighted output value may be used.")
        score -= Decimal("8")

    if completeness.completeness_by_area.get("shipment_inbound_trust") == Decimal("1.00"):
        boosts.append("Shipment trust calibrated.")

    if inventory is not None:
        if inventory.visibility_confidence is not None and inventory.visibility_confidence >= Decimal("0.75"):
            boosts.append("Strong visibility confidence supports operational reasoning.")
            score += Decimal("3")
        if inventory.visibility_confidence is not None and inventory.visibility_confidence < Decimal("0.50"):
            penalties.append("Weak inbound visibility reduces operational precision.")
            score -= Decimal("8")
        if inventory.visibility_uncertain_quantity_mt > 0:
            penalties.append("Visibility uncertainty exists in physical inbound protection.")
            score -= Decimal("4")
        if inventory.freshness_status in {"stale", "critical"}:
            penalties.append("Stale inventory visibility reduces operational precision.")
            score -= Decimal("6")

    if any("Supplier-context evidence insufficient" in reason for reason in completeness.confidence_reason_chain):
        penalties.append("Supplier-context evidence insufficient; neutral reliability fallback may apply.")
        score -= Decimal("4")
    elif completeness.completeness_by_area.get("supplier_context") == Decimal("1.00"):
        boosts.append("Strong supplier-context history is available.")

    score = clamp_score(score)
    band = confidence_band(score)
    return RiskOperationalTrustResult(
        risk_precision_band=band,
        reasoning_strength=reasoning_strength(score),
        trusted_signal_count=trusted,
        weak_signal_count=weak,
        missing_signal_count=missing,
        trust_penalties=dedupe(penalties),
        trust_boosts=dedupe(boosts),
        operational_trust_score=score,
    )


def resolve_plant_material(
    db: Session,
    *,
    tenant_id: int,
    plant_reference: str | None,
    material_reference: str | None,
) -> tuple[Plant, Material] | tuple[None, None]:
    if plant_reference is None or material_reference is None:
        return None, None
    plant = db.scalar(
        select(Plant).where(Plant.tenant_id == tenant_id, Plant.code == plant_reference)
    )
    material = db.scalar(
        select(Material).where(
            Material.tenant_id == tenant_id,
            Material.code == material_reference,
        )
    )
    if plant is None or material is None:
        return None, None
    return plant, material


def score_area(
    area: str,
    is_configured: bool,
    area_scores: dict[str, Decimal],
    missing: list[str],
    reasons: list[str],
    *,
    configured_text: str,
    missing_text: str,
) -> None:
    if is_configured:
        area_scores[area] = Decimal("1.00")
        reasons.append(configured_text)
    else:
        area_scores[area] = Decimal("0.00")
        missing.append(missing_text)
        reasons.append(missing_text)


def product_process_dependency_score(
    db: Session,
    *,
    tenant_id: int,
    material_id: int,
) -> Decimal:
    process_ids = list(
        db.scalars(
            select(MaterialProcessDependency.process_id).where(
                MaterialProcessDependency.tenant_id == tenant_id,
                MaterialProcessDependency.material_id == material_id,
                MaterialProcessDependency.is_active.is_(True),
            )
        )
    )
    if not process_ids:
        return Decimal("0.00")
    product_count = db.scalar(
        select(func.count(ProcessProductDependency.id)).where(
            ProcessProductDependency.tenant_id == tenant_id,
            ProcessProductDependency.process_id.in_(process_ids),
            ProcessProductDependency.is_active.is_(True),
        )
    )
    return Decimal("1.00") if product_count else Decimal("0.50")


def supplier_context_score(
    db: Session,
    *,
    tenant_id: int,
    plant_id: int,
    material_id: int,
) -> tuple[Decimal, str]:
    count = db.scalar(
        select(func.count(Shipment.id)).where(
            Shipment.tenant_id == tenant_id,
            Shipment.plant_id == plant_id,
            Shipment.material_id == material_id,
            Shipment.supplier_name.is_not(None),
        )
    ) or 0
    if count >= 3:
        return Decimal("1.00"), f"Supplier-context evidence available from {count} shipments."
    if count > 0:
        return (
            Decimal("0.50"),
            f"Supplier-context evidence insufficient; {count} shipment samples available.",
        )
    return Decimal("0.00"), "Supplier-context evidence insufficient; no shipment samples available."


def inventory_visibility_score(
    inventory: InventoryContinuityResult | None,
) -> tuple[Decimal, str]:
    if inventory is None:
        return Decimal("0.00"), "Inventory visibility is unavailable for this context."
    if inventory.freshness_status in {"stale", "critical"}:
        return (
            Decimal("0.40"),
            f"Inventory visibility freshness is {inventory.freshness_status}.",
        )
    if inventory.cover_confidence_score is not None and inventory.cover_confidence_score < Decimal("0.70"):
        return (
            Decimal("0.60"),
            f"Inventory cover confidence is {inventory.cover_confidence_score}.",
        )
    return Decimal("1.00"), "Inventory visibility is acceptable."


def shipment_visibility_score(
    db: Session,
    *,
    tenant_id: int,
    plant_id: int,
    material_id: int,
) -> tuple[Decimal, str]:
    shipments = list(
        db.scalars(
            select(Shipment).where(
                Shipment.tenant_id == tenant_id,
                Shipment.plant_id == plant_id,
                Shipment.material_id == material_id,
                Shipment.current_state.in_(ACTIVE_SHIPMENT_STATES),
            )
        )
    )
    if not shipments:
        return Decimal("0.00"), "No active shipment visibility signals are available."
    tracked = [
        shipment
        for shipment in shipments
        if shipment.last_tracking_update_at is not None or shipment.latest_update_at is not None
    ]
    if not tracked:
        return Decimal("0.40"), "Active shipments exist but tracking/update timestamps are missing."
    return Decimal("1.00"), f"Shipment visibility signals are available from {len(tracked)} active shipments."


def confidence_band(score: Decimal) -> str:
    if score >= Decimal("85"):
        return "high"
    if score >= Decimal("65"):
        return "moderate"
    if score >= Decimal("40"):
        return "low"
    return "unknown"


def reasoning_strength(score: Decimal) -> str:
    if score >= Decimal("75"):
        return "strong"
    if score >= Decimal("45"):
        return "partial"
    return "weak"


def quantize_score(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def quantize_ratio(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def clamp_score(value: Decimal) -> Decimal:
    return max(Decimal("0.00"), min(Decimal("100.00"), quantize_score(value)))


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
