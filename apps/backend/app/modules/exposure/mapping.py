from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.modules.relationships.graph import (
    GraphScope,
    OperationalRelationshipGraph,
    build_operational_relationship_graph,
    relevant_risk_candidates,
    scope_from_inputs,
)
from app.modules.rules.engine import RiskCandidate
from app.schemas.context import RequestContext


class ExposureTrustSummary(BaseModel):
    lowest_confidence_score: Decimal | None = None
    worst_freshness_status: str | None = None
    warnings: list[str] = Field(default_factory=list)


class OperationalExposureMapping(BaseModel):
    plant_reference: str | None = None
    material_reference: str | None = None
    shipment_reference: str | None = None
    estimated_exposure_date: datetime | None = None
    days_until_exposure: Decimal | None = None
    exposure_level: str
    exposure_basis: str
    operational_reason: str
    trust_summary: ExposureTrustSummary
    related_risk_types: list[str]
    timeline_event_count: int


def build_exposure_mapping(
    db: Session,
    context: RequestContext,
    *,
    plant_reference: str | None = None,
    material_reference: str | None = None,
    shipment_reference: str | None = None,
    risk_candidate: RiskCandidate | None = None,
    now: datetime | None = None,
) -> OperationalExposureMapping:
    evaluated_at = ensure_utc(now or datetime.now(UTC))
    graph = build_operational_relationship_graph(
        db,
        context,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
        risk_candidate=risk_candidate,
        now=evaluated_at,
    )
    scope = scope_from_inputs(
        plant_reference=graph.context.plant_reference,
        material_reference=graph.context.material_reference,
        shipment_reference=graph.context.shipment_reference,
        risk_candidate=risk_candidate,
    )
    candidates = relevant_risk_candidates(
        db,
        context,
        scope,
        risk_candidate=risk_candidate,
        now=evaluated_at,
    )
    return exposure_from_graph(graph, scope, candidates, evaluated_at)


def exposure_from_graph(
    graph: OperationalRelationshipGraph,
    scope: GraphScope,
    candidates: list[RiskCandidate],
    now: datetime,
) -> OperationalExposureMapping:
    inventory = graph.summary.inventory_continuity or {}
    shipment = graph.summary.shipment_continuity or {}
    related_risk_types = sorted({candidate.risk_type for candidate in candidates})
    exposure_date = inventory.get("projected_exhaustion_date")
    days_until = days_until_exposure(exposure_date, now)
    days_of_cover = decimal_or_none(inventory.get("days_of_cover"))
    eta_slip_days = decimal_or_none(shipment.get("eta_slip_days"))
    shipment_status = shipment.get("status")

    basis = "unknown"
    level = "unknown"
    if inbound_delay_against_cover(
        shipment_status,
        days_of_cover,
        eta_slip_days,
        related_risk_types,
    ):
        basis = "inbound_delay_against_cover"
        level = inbound_delay_level(exposure_date, days_of_cover, eta_slip_days, now)
    elif exposure_date is not None:
        basis = "projected_stockout"
        level = level_for_exposure_date(ensure_utc(exposure_date), days_of_cover, now)
    elif days_of_cover is not None and days_of_cover <= Decimal("10"):
        basis = "projected_stockout"
        level = "watch"
    elif shipment_status == "degraded":
        basis = "shipment_degradation"
        level = "watch"
    elif graph.summary.confidence_summary.worst_freshness_status in {"stale", "critical"}:
        basis = "stale_visibility"
        level = "watch"
    elif missing_precision(inventory, shipment, scope):
        basis = "unknown"
        level = "unknown"

    return OperationalExposureMapping(
        plant_reference=scope.plant_reference,
        material_reference=scope.material_reference,
        shipment_reference=scope.shipment_reference,
        estimated_exposure_date=exposure_date,
        days_until_exposure=days_until,
        exposure_level=level,
        exposure_basis=basis,
        operational_reason=operational_reason(
            plant_reference=scope.plant_reference,
            material_reference=scope.material_reference,
            shipment_reference=scope.shipment_reference,
            basis=basis,
            level=level,
            days_until=days_until,
            days_of_cover=days_of_cover,
            shipment_status=shipment_status,
        ),
        trust_summary=trust_summary(graph),
        related_risk_types=related_risk_types,
        timeline_event_count=graph.summary.timeline_event_count,
    )


def inbound_delay_against_cover(
    shipment_status: str | None,
    days_of_cover: Decimal | None,
    eta_slip_days: Decimal | None,
    related_risk_types: list[str],
) -> bool:
    if "inbound_delay_against_cover" in related_risk_types:
        return True
    return (
        shipment_status == "degraded"
        and days_of_cover is not None
        and eta_slip_days is not None
        and days_of_cover <= eta_slip_days
    )


def inbound_delay_level(
    exposure_date: datetime | None,
    days_of_cover: Decimal | None,
    eta_slip_days: Decimal | None,
    now: datetime,
) -> str:
    if exposure_date is not None and ensure_utc(exposure_date) <= now + timedelta(hours=48):
        return "immediate"
    if (
        days_of_cover is not None
        and eta_slip_days is not None
        and days_of_cover <= eta_slip_days
    ):
        return "immediate" if days_of_cover <= Decimal("2") else "near_term"
    return "near_term"


def level_for_exposure_date(
    exposure_date: datetime,
    days_of_cover: Decimal | None,
    now: datetime,
) -> str:
    if exposure_date <= now + timedelta(hours=48):
        return "immediate"
    if exposure_date <= now + timedelta(days=5):
        return "near_term"
    if days_of_cover is not None and days_of_cover <= Decimal("10"):
        return "watch"
    return "unknown"


def days_until_exposure(
    exposure_date: datetime | None,
    now: datetime,
) -> Decimal | None:
    if exposure_date is None:
        return None
    seconds = (ensure_utc(exposure_date) - now).total_seconds()
    return (Decimal(str(seconds)) / Decimal("86400")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def operational_reason(
    *,
    plant_reference: str | None,
    material_reference: str | None,
    shipment_reference: str | None,
    basis: str,
    level: str,
    days_until: Decimal | None,
    days_of_cover: Decimal | None,
    shipment_status: str | None,
) -> str:
    plant = plant_reference or "unknown plant"
    material = material_reference or "unknown material"
    shipment = shipment_reference or "unknown shipment"
    if basis == "inbound_delay_against_cover":
        return (
            f"Material {material} at plant {plant} is exposed because inbound shipment "
            f"{shipment} is degraded while available cover is {days_of_cover} days."
        )
    if basis == "projected_stockout" and days_until is not None:
        return (
            f"Material {material} at plant {plant} is projected to exhaust in "
            f"{days_until} days."
        )
    if basis == "projected_stockout":
        return (
            f"Material {material} at plant {plant} has {days_of_cover} days of cover, "
            "within the watch threshold."
        )
    if basis == "shipment_degradation":
        return (
            f"Shipment {shipment} is {shipment_status}, creating watch-level exposure "
            f"for material {material} at plant {plant}."
        )
    if basis == "stale_visibility":
        return (
            f"Operational visibility for material {material} at plant {plant} is stale, "
            "so exposure is tracked as watch."
        )
    if level == "unknown":
        return (
            f"Exposure timing for material {material} at plant {plant} is unknown because "
            "required consumption or shipment timing data is unavailable."
        )
    return "Operational exposure context is available but does not breach exposure thresholds."


def trust_summary(graph: OperationalRelationshipGraph) -> ExposureTrustSummary:
    confidence = graph.summary.confidence_summary
    warnings = []
    if confidence.worst_freshness_status in {"stale", "critical"}:
        warnings.append(f"Operational signal freshness is {confidence.worst_freshness_status}")
    if (
        confidence.lowest_confidence_score is not None
        and confidence.lowest_confidence_score < Decimal("50")
    ):
        warnings.append(
            f"Operational signal confidence is low at {confidence.lowest_confidence_score}"
        )
    return ExposureTrustSummary(
        lowest_confidence_score=confidence.lowest_confidence_score,
        worst_freshness_status=confidence.worst_freshness_status,
        warnings=warnings,
    )


def missing_precision(
    inventory: dict,
    shipment: dict,
    scope: GraphScope,
) -> bool:
    missing_consumption = bool(inventory) and inventory.get("days_of_cover") is None
    missing_eta = bool(scope.shipment_reference) and shipment.get("eta") is None
    return missing_consumption or missing_eta or (not inventory and not shipment)


def decimal_or_none(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
