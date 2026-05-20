from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import Shipment
from app.modules.shipments.schemas import ShipmentContinuityResult
from app.modules.shipments.visibility_confidence import (
    VisibilityConfidenceResult,
    calculate_visibility_confidence,
    quantize_decimal,
)
from app.modules.stock.schemas import InventoryContinuityResult
from app.modules.suppliers.reliability_context import (
    SupplierReliabilityContextResult,
    calculate_supplier_reliability_context,
    supplier_reliability_modifier,
)

DEFAULT_CRITICAL_THRESHOLD_DAYS = Decimal("2")
DEFAULT_WARNING_THRESHOLD_DAYS = Decimal("5")

ETA_THREAT_BY_BEHAVIOR = {
    "stable": "low",
    "recovering": "low",
    "drifting": "medium",
    "degraded": "high",
    "repeatedly_drifting": "high",
    "volatile": "critical",
    "unknown": "watch",
}

THREAT_RANK = {"low": 0, "watch": 1, "medium": 2, "high": 3, "critical": 4}
SEVERITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class InboundDelayCoverResult(BaseModel):
    applies: bool
    risk_type: str = "inbound_delay_against_cover"
    severity: str
    exposure_level: str
    days_of_cover: Decimal | None
    trusted_days_of_cover: Decimal | None
    eta_delay_hours: Decimal
    eta_behavior_status: str
    visibility_confidence: Decimal | None
    supplier_reliability_band: str | None = None
    physical_inbound_quantity_mt: Decimal
    trusted_inbound_protection_mt: Decimal
    visibility_uncertain_quantity_mt: Decimal
    delay_exceeds_cover: bool
    delay_exceeds_threshold_window: bool
    trusted_protection_weak: bool
    reason_chain: list[str]


def evaluate_inbound_delay_cover_intelligence(
    shipment_continuity: ShipmentContinuityResult,
    inventory: InventoryContinuityResult,
    *,
    db: Session | None = None,
    tenant_id: int | None = None,
    shipment: Shipment | None = None,
    now: datetime | None = None,
) -> InboundDelayCoverResult:
    days = inventory.days_of_cover
    trusted_days = inventory.trusted_days_of_cover
    threshold_days, warning_days, threshold_reasons = threshold_context(inventory)
    eta_delay_hours = eta_delay_hours_for(shipment_continuity, shipment)
    visibility: VisibilityConfidenceResult | None = None
    supplier: SupplierReliabilityContextResult | None = None
    if shipment is not None:
        visibility = calculate_visibility_confidence(shipment, now=now)
        if db is not None and tenant_id is not None:
            supplier = calculate_supplier_reliability_context(
                db,
                tenant_id=tenant_id,
                shipment=shipment,
                visibility_result=visibility,
                now=now,
            )

    eta_behavior = (
        visibility.eta_behavior_status
        if visibility is not None
        else fallback_eta_behavior(shipment_continuity)
    )
    eta_threat = ETA_THREAT_BY_BEHAVIOR.get(eta_behavior, "watch")
    physical, trusted, uncertain, visibility_confidence = inbound_quantities(
        inventory,
        visibility,
        supplier,
    )
    trusted_ratio = trusted / physical if physical > 0 else Decimal("0")
    trusted_weak = trusted_ratio < Decimal("0.50")
    cover_pressure = cover_pressure_for(days, threshold_days, warning_days)
    delay_exceeds_cover = bool(days is not None and eta_delay_hours / Decimal("24") >= days)
    delay_exceeds_threshold_window = bool(
        days is not None
        and eta_delay_hours / Decimal("24") >= max(Decimal("0"), days - threshold_days)
    )

    reasons = [
        *threshold_reasons,
        f"Cover pressure is {cover_pressure}.",
        f"ETA behavior status is {eta_behavior}, mapped to {eta_threat} ETA threat.",
        f"ETA delay is {eta_delay_hours} hours.",
        f"Physical inbound quantity remains unchanged at {physical} MT.",
        (
            f"trusted inbound protection is {trusted} MT and visibility uncertainty is "
            f"{uncertain} MT; risk is due to confidence and cover timing, not missing material."
        ),
        f"Trusted inbound protection ratio is {quantize_decimal(trusted_ratio)}.",
    ]
    if visibility is not None:
        reasons.append(f"Visibility confidence is {visibility.visibility_confidence}.")
    if supplier is not None:
        reasons.append(f"Supplier reliability band is {supplier.reliability_band}.")
    reasons.append(
        f"Delay exceeds full cover: {delay_exceeds_cover}; delay can push material into "
        f"critical threshold window: {delay_exceeds_threshold_window}."
    )

    severity = severity_for_delay_cover(
        cover_pressure=cover_pressure,
        eta_threat=eta_threat,
        trusted_protection_weak=trusted_weak,
        delay_exceeds_threshold_window=delay_exceeds_threshold_window,
    )
    if (
        supplier is not None
        and supplier.reliability_band == "weak"
        and severity
        in {
            "low",
            "medium",
        }
    ):
        severity = increase_severity(severity)
        reasons.append("Weak supplier reliability increased concern for an already risky delay.")

    exposure_level = exposure_level_for(severity, days, threshold_days, warning_days)
    applies = severity != "none"
    if not applies:
        reasons.append(
            "No inbound delay risk created because ETA behavior is stable or recovering, "
            "trusted protection is strong, and cover pressure is normal."
        )
    else:
        reasons.append(f"Inbound delay against cover severity is {severity}.")

    return InboundDelayCoverResult(
        applies=applies,
        severity=severity,
        exposure_level=exposure_level,
        days_of_cover=days,
        trusted_days_of_cover=trusted_days,
        eta_delay_hours=eta_delay_hours,
        eta_behavior_status=eta_behavior,
        visibility_confidence=visibility_confidence,
        supplier_reliability_band=supplier.reliability_band if supplier is not None else None,
        physical_inbound_quantity_mt=physical,
        trusted_inbound_protection_mt=trusted,
        visibility_uncertain_quantity_mt=uncertain,
        delay_exceeds_cover=delay_exceeds_cover,
        delay_exceeds_threshold_window=delay_exceeds_threshold_window,
        trusted_protection_weak=trusted_weak,
        reason_chain=reasons,
    )


def threshold_context(
    inventory: InventoryContinuityResult,
) -> tuple[Decimal, Decimal, list[str]]:
    threshold_days = inventory.threshold_days or DEFAULT_CRITICAL_THRESHOLD_DAYS
    warning_days = inventory.warning_days or DEFAULT_WARNING_THRESHOLD_DAYS
    if inventory.threshold_days is not None or inventory.warning_days is not None:
        return (
            threshold_days,
            warning_days,
            [
                f"Configured critical threshold used: {threshold_days} days.",
                f"Configured warning threshold used: {warning_days} days.",
            ],
        )
    return (
        threshold_days,
        warning_days,
        [
            f"Fallback critical threshold used: {threshold_days} days.",
            f"Fallback warning threshold used: {warning_days} days.",
        ],
    )


def eta_delay_hours_for(
    shipment_continuity: ShipmentContinuityResult,
    shipment: Shipment | None,
) -> Decimal:
    if (
        shipment is not None
        and shipment.current_eta is not None
        and shipment.planned_eta is not None
    ):
        seconds = (shipment.current_eta - shipment.planned_eta).total_seconds()
        return quantize_decimal(max(Decimal("0"), Decimal(str(seconds)) / Decimal("3600")))
    return quantize_decimal((shipment_continuity.eta_slip_days or Decimal("0")) * Decimal("24"))


def fallback_eta_behavior(shipment_continuity: ShipmentContinuityResult) -> str:
    if shipment_continuity.status == "degraded":
        if (
            shipment_continuity.eta_slip_days is not None
            and shipment_continuity.eta_slip_days > Decimal("1")
        ):
            return "degraded"
        return "drifting"
    if shipment_continuity.status == "watch":
        return "unknown"
    return "stable"


def inbound_quantities(
    inventory: InventoryContinuityResult,
    visibility: VisibilityConfidenceResult | None,
    supplier: SupplierReliabilityContextResult | None,
) -> tuple[Decimal, Decimal, Decimal, Decimal | None]:
    if visibility is None:
        physical = inventory.physical_inbound_quantity_mt
        trusted = inventory.trusted_inbound_protection_mt or inventory.trusted_inbound_quantity
        uncertain = (
            inventory.visibility_uncertain_quantity_mt or inventory.uncertain_inbound_quantity
        )
        return physical, trusted, uncertain, inventory.visibility_confidence

    modifier = (
        supplier_reliability_modifier(supplier.reliability_band)
        if supplier is not None
        else Decimal("0.00")
    )
    adjusted_confidence = max(
        Decimal("0.00"),
        min(Decimal("1.00"), visibility.visibility_confidence + modifier),
    )
    physical = visibility.physical_inbound_quantity_mt
    trusted = quantize_decimal(physical * adjusted_confidence)
    uncertain = quantize_decimal(physical - trusted)
    return physical, trusted, uncertain, quantize_decimal(adjusted_confidence)


def cover_pressure_for(
    days_of_cover: Decimal | None,
    threshold_days: Decimal,
    warning_days: Decimal,
) -> str:
    if days_of_cover is None:
        return "unknown"
    if days_of_cover <= threshold_days:
        return "critical"
    if days_of_cover <= warning_days:
        return "warning"
    return "normal"


def severity_for_delay_cover(
    *,
    cover_pressure: str,
    eta_threat: str,
    trusted_protection_weak: bool,
    delay_exceeds_threshold_window: bool,
) -> str:
    threat_rank = THREAT_RANK.get(eta_threat, THREAT_RANK["watch"])
    if (
        cover_pressure == "critical"
        and threat_rank >= THREAT_RANK["high"]
        and trusted_protection_weak
    ):
        return "critical"
    if cover_pressure in {"warning", "critical"} and threat_rank >= THREAT_RANK["medium"]:
        return "high"
    if delay_exceeds_threshold_window and trusted_protection_weak:
        return "high"
    if cover_pressure == "warning" or trusted_protection_weak or eta_threat == "medium":
        return "medium"
    if eta_threat in {"watch", "high", "critical"}:
        return "low"
    return "none"


def exposure_level_for(
    severity: str,
    days_of_cover: Decimal | None,
    threshold_days: Decimal,
    warning_days: Decimal,
) -> str:
    if severity == "none":
        return "none"
    if severity == "critical" or (days_of_cover is not None and days_of_cover <= threshold_days):
        return "immediate"
    if severity == "high" or (days_of_cover is not None and days_of_cover <= warning_days):
        return "near_term"
    return "watch"


def increase_severity(severity: str) -> str:
    rank = min(SEVERITY_RANK[severity] + 1, SEVERITY_RANK["critical"])
    return next(value for value, item_rank in SEVERITY_RANK.items() if item_rank == rank)
