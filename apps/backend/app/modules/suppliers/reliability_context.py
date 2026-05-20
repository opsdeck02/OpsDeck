from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Shipment
from app.modules.shipments.visibility_confidence import (
    VisibilityConfidenceResult,
    abnormal_visibility_behavior,
    calculate_eta_behavior,
    calculate_visibility_confidence,
    infer_visibility_profile,
)

MIN_CONTEXT_SAMPLE_SIZE = 3
RECENT_WINDOW_DAYS = 90
MAX_SAMPLE_SIZE = 10

RELIABILITY_MODIFIERS = {
    "strong": Decimal("0.03"),
    "acceptable": Decimal("0.00"),
    "watch": Decimal("-0.05"),
    "weak": Decimal("-0.10"),
    "unknown": Decimal("0.00"),
}


class SupplierReliabilityContextResult(BaseModel):
    supplier_id: uuid.UUID | None
    plant_id: int | None
    material_id: int | None
    reliability_context_key: str
    reliability_scope: str
    contextual_reliability_score: Decimal
    reliability_band: str
    on_time_performance_ratio: Decimal | None
    eta_behavior_penalty: Decimal
    visibility_confidence_penalty: Decimal
    fulfillment_penalty: Decimal | None = None
    sample_size: int
    confidence_in_score: str
    reason_chain: list[str]


def calculate_supplier_reliability_context(
    db: Session,
    *,
    tenant_id: int,
    shipment: Shipment,
    visibility_result: VisibilityConfidenceResult | None = None,
    now: datetime | None = None,
) -> SupplierReliabilityContextResult:
    evaluated_at = ensure_utc(now or datetime.now(UTC))
    supplier_id = shipment.supplier_id
    if supplier_id is None:
        return unknown_supplier_result(shipment, "Supplier identity is missing.")

    scope, samples = evidence_for_supplier_context(
        db,
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        plant_id=shipment.plant_id,
        material_id=shipment.material_id,
        now=evaluated_at,
    )
    reasons = [
        f"Supplier reliability assessed using {scope} context with {len(samples)} shipments."
    ]

    if len(samples) < MIN_CONTEXT_SAMPLE_SIZE:
        score = Decimal("0.70")
        confidence = "low"
        on_time_ratio = None
        avg_visibility = None
        reasons.append("Insufficient supplier-context history; neutral reliability applied.")
    else:
        on_time_ratio = on_time_performance_ratio(samples)
        avg_visibility = average_visibility_confidence(samples, evaluated_at)
        score = quantize_decimal(on_time_ratio * Decimal("0.65") + avg_visibility * Decimal("0.35"))
        confidence = confidence_for_sample_size(len(samples))
        reasons.append(f"On-time performance ratio is {on_time_ratio}.")
        reasons.append(f"Average visibility confidence is {avg_visibility}.")

    current_visibility = visibility_result or calculate_visibility_confidence(
        shipment, now=evaluated_at
    )
    eta_penalty = eta_behavior_adjustment(current_visibility.eta_behavior_status)
    visibility_penalty = (
        Decimal("-0.10")
        if current_visibility.visibility_confidence < Decimal("0.50")
        else Decimal("0.00")
    )
    abnormal_penalty = (
        Decimal("-0.15") if abnormal_visibility_behavior(shipment) else Decimal("0.00")
    )
    score = clamp(score + eta_penalty + visibility_penalty + abnormal_penalty)
    if eta_penalty:
        reasons.append(
            f"Current shipment ETA behavior {current_visibility.eta_behavior_status} "
            f"applied {abs(eta_penalty)} reliability penalty."
        )
    if visibility_penalty:
        reasons.append("Weak current visibility confidence applied 0.10 reliability penalty.")
    if abnormal_penalty:
        reasons.append("Abnormal current shipment state applied 0.15 reliability penalty.")

    band = reliability_band(score)
    reasons.append(f"Final contextual supplier reliability band is {band}.")

    return SupplierReliabilityContextResult(
        supplier_id=supplier_id,
        plant_id=shipment.plant_id,
        material_id=shipment.material_id,
        reliability_context_key=context_key(
            supplier_id,
            shipment.plant_id,
            shipment.material_id,
            scope,
        ),
        reliability_scope=scope,
        contextual_reliability_score=score,
        reliability_band=band,
        on_time_performance_ratio=on_time_ratio,
        eta_behavior_penalty=eta_penalty,
        visibility_confidence_penalty=visibility_penalty,
        sample_size=len(samples),
        confidence_in_score=confidence,
        reason_chain=reasons,
    )


def evidence_for_supplier_context(
    db: Session,
    *,
    tenant_id: int,
    supplier_id: uuid.UUID,
    plant_id: int,
    material_id: int,
    now: datetime,
) -> tuple[str, list[Shipment]]:
    priorities = [
        ("supplier_material_plant", {"plant_id": plant_id, "material_id": material_id}),
        ("supplier_material", {"material_id": material_id}),
        ("supplier_global", {}),
    ]
    for scope, filters in priorities:
        samples = supplier_shipments(
            db,
            tenant_id=tenant_id,
            supplier_id=supplier_id,
            now=now,
            **filters,
        )
        if samples:
            return scope, samples
    return "unknown", []


def supplier_shipments(
    db: Session,
    *,
    tenant_id: int,
    supplier_id: uuid.UUID,
    now: datetime,
    plant_id: int | None = None,
    material_id: int | None = None,
) -> list[Shipment]:
    since = now - timedelta(days=RECENT_WINDOW_DAYS)
    query = select(Shipment).where(
        Shipment.tenant_id == tenant_id,
        Shipment.supplier_id == supplier_id,
        Shipment.current_eta >= since,
    )
    if plant_id is not None:
        query = query.where(Shipment.plant_id == plant_id)
    if material_id is not None:
        query = query.where(Shipment.material_id == material_id)
    return list(db.scalars(query.order_by(Shipment.current_eta.desc()).limit(MAX_SAMPLE_SIZE)))


def on_time_performance_ratio(shipments: list[Shipment]) -> Decimal:
    if not shipments:
        return Decimal("0.00")
    on_time = 0
    for shipment in shipments:
        profile = infer_visibility_profile(shipment)
        behavior = calculate_eta_behavior(
            shipment,
            visibility_profile=profile,
            hours_since_update=None,
            expected_visibility_cadence_hours=Decimal("24"),
            abnormal_visibility=abnormal_visibility_behavior(shipment),
        )
        if behavior.eta_behavior_status in {"stable", "recovering"}:
            on_time += 1
    return quantize_decimal(Decimal(on_time) / Decimal(len(shipments)))


def average_visibility_confidence(shipments: list[Shipment], now: datetime) -> Decimal:
    if not shipments:
        return Decimal("0.00")
    total = sum(
        (
            calculate_visibility_confidence(shipment, now=now).visibility_confidence
            for shipment in shipments
        ),
        start=Decimal("0"),
    )
    return quantize_decimal(total / Decimal(len(shipments)))


def eta_behavior_adjustment(status: str) -> Decimal:
    if status == "degraded":
        return Decimal("-0.10")
    if status == "repeatedly_drifting":
        return Decimal("-0.15")
    if status == "volatile":
        return Decimal("-0.20")
    return Decimal("0.00")


def supplier_reliability_modifier(band: str) -> Decimal:
    return RELIABILITY_MODIFIERS.get(band, Decimal("0.00"))


def confidence_for_sample_size(sample_size: int) -> str:
    if sample_size >= 6:
        return "high"
    if sample_size >= MIN_CONTEXT_SAMPLE_SIZE:
        return "medium"
    if sample_size > 0:
        return "low"
    return "unknown"


def reliability_band(score: Decimal) -> str:
    if score >= Decimal("0.85"):
        return "strong"
    if score >= Decimal("0.70"):
        return "acceptable"
    if score >= Decimal("0.50"):
        return "watch"
    return "weak"


def unknown_supplier_result(shipment: Shipment, reason: str) -> SupplierReliabilityContextResult:
    return SupplierReliabilityContextResult(
        supplier_id=shipment.supplier_id,
        plant_id=shipment.plant_id,
        material_id=shipment.material_id,
        reliability_context_key="unknown",
        reliability_scope="unknown",
        contextual_reliability_score=Decimal("0.50"),
        reliability_band="unknown",
        on_time_performance_ratio=None,
        eta_behavior_penalty=Decimal("0.00"),
        visibility_confidence_penalty=Decimal("0.00"),
        sample_size=0,
        confidence_in_score="unknown",
        reason_chain=[reason, "Supplier reliability context is unknown."],
    )


def context_key(
    supplier_id: uuid.UUID,
    plant_id: int | None,
    material_id: int | None,
    scope: str,
) -> str:
    if scope == "supplier_material_plant":
        return f"supplier:{supplier_id}:plant:{plant_id}:material:{material_id}"
    if scope == "supplier_material":
        return f"supplier:{supplier_id}:material:{material_id}"
    if scope == "supplier_global":
        return f"supplier:{supplier_id}:global"
    return "unknown"


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def clamp(value: Decimal) -> Decimal:
    return max(Decimal("0.00"), min(Decimal("1.00"), quantize_decimal(value)))
