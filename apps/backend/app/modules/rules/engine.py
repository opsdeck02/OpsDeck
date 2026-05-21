from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OperationalEvent, Shipment, StockSnapshot
from app.modules.impact.schemas import OperationalInterruptionImpact
from app.modules.recommendations.operational_actions import OperationalActionRecommendation
from app.modules.rules.inbound_delay_cover import evaluate_inbound_delay_cover_intelligence
from app.modules.shipments.continuity import calculate_shipment_continuity_for
from app.modules.shipments.schemas import ShipmentContinuityResult
from app.modules.stock.continuity import calculate_inventory_continuity_for
from app.modules.stock.schemas import InventoryContinuityResult
from app.modules.trust.operational import (
    ConfigurationCompletenessResult,
    RiskOperationalTrustResult,
)
from app.schemas.context import RequestContext

FRESHNESS_ORDER = {"fresh": 0, "delayed": 1, "unknown": 2, "stale": 3, "critical": 4}
DEFAULT_STOCKOUT_ALERT_HOURS = Decimal("48")


class ContributingSignal(BaseModel):
    signal_type: str
    event_id: str | None = None
    source_type: str | None = None
    occurred_at: datetime | None = None
    confidence_score: Decimal | None = None
    freshness_status: str | None = None
    description: str


class OperationalContext(BaseModel):
    plant_reference: str | None = None
    material_reference: str | None = None
    shipment_reference: str | None = None
    supplier_reference: str | None = None
    days_of_cover: Decimal | None = None
    projected_exhaustion_date: datetime | None = None
    shipment_continuity_status: str | None = None


class TrustContext(BaseModel):
    lowest_confidence_score: Decimal | None = None
    worst_freshness_status: str | None = None
    trust_warnings: list[str] = []


class RiskExplainability(BaseModel):
    summary: str
    primary_driver: str
    contributing_signals: list[ContributingSignal]
    operational_context: OperationalContext
    trust_context: TrustContext
    reason_chain: list[str]


class RiskCandidate(BaseModel):
    risk_type: str
    severity: str
    plant_reference: str | None = None
    material_reference: str | None = None
    shipment_reference: str | None = None
    supplier_reference: str | None = None
    days_of_cover: Decimal | None = None
    projected_exhaustion_date: datetime | None = None
    continuity_status: str | None = None
    confidence_score: Decimal | None = None
    freshness_status: str | None = None
    rule_reasons: list[str]
    source_event_ids: list[int] = []
    recommended_owner_role: str | None = None
    explainability: RiskExplainability | None = None
    escalation_state: str | None = None
    escalation_score: Decimal | None = None
    escalation_reason: str | None = None
    prior_days_of_cover: Decimal | None = None
    current_days_of_cover: Decimal | None = None
    days_of_cover_delta: Decimal | None = None
    prior_shipment_delay_hours: Decimal | None = None
    current_shipment_delay_hours: Decimal | None = None
    shipment_delay_delta_hours: Decimal | None = None
    prior_severity: str | None = None
    current_severity: str | None = None
    prior_exposure_level: str | None = None
    current_exposure_level: str | None = None
    operational_interruption_impact: OperationalInterruptionImpact | None = None
    operational_recommendations: list[OperationalActionRecommendation] = []
    configuration_completeness: ConfigurationCompletenessResult | None = None
    operational_trust: RiskOperationalTrustResult | None = None


def evaluate_rule_based_risks(
    db: Session,
    context: RequestContext,
    *,
    now: datetime | None = None,
) -> list[RiskCandidate]:
    evaluated_at = ensure_utc(now or datetime.now(UTC))
    inventory_items = inventory_continuity_items(db, context, now=evaluated_at)
    shipment_items = shipment_continuity_items(db, context, now=evaluated_at)
    events = list(
        db.scalars(select(OperationalEvent).where(OperationalEvent.tenant_id == context.tenant_id))
    )

    candidates: list[RiskCandidate] = []
    for inventory in inventory_items:
        candidates.extend(evaluate_inventory_rules(inventory, now=evaluated_at))

    inventory_by_context = {
        (item.plant_reference, item.material_reference): item for item in inventory_items
    }
    shipment_models_by_reference = {
        item.shipment_id: item
        for item in db.scalars(select(Shipment).where(Shipment.tenant_id == context.tenant_id))
    }
    for shipment in shipment_items:
        candidates.extend(evaluate_shipment_rules(shipment))
        inventory = inventory_by_context.get(
            (shipment.linked_plant_reference, shipment.linked_material_reference)
        )
        if inventory is not None:
            candidates.extend(
                evaluate_inbound_delay_against_cover(
                    shipment,
                    inventory,
                    db=db,
                    tenant_id=context.tenant_id,
                    shipment_model=shipment_models_by_reference.get(shipment.shipment_reference),
                    now=evaluated_at,
                )
            )

    for event in events:
        candidates.extend(evaluate_event_trust_rules(event))

    return attach_explainability(candidates, events)


def evaluate_inventory_rules(
    continuity: InventoryContinuityResult,
    *,
    now: datetime | None = None,
) -> list[RiskCandidate]:
    candidates: list[RiskCandidate] = []
    days = continuity.days_of_cover
    if days is None:
        reserve_reasons = protected_reserve_reasons(continuity)
        if continuity.usable_quantity <= 0:
            candidates.append(
                with_explainability(
                    RiskCandidate(
                        risk_type="days_of_cover_breach",
                        severity="medium",
                        plant_reference=continuity.plant_reference,
                        material_reference=continuity.material_reference,
                        rule_reasons=[
                            "Days of cover is unknown because consumption rate is unavailable",
                            "Usable quantity is zero or negative",
                            *reserve_reasons,
                        ],
                        recommended_owner_role="materials_planner",
                    )
                )
            )
        elif reserve_reasons:
            candidates.append(protected_reserve_candidate(continuity, reserve_reasons))
        return candidates

    severity = severity_for_days_of_cover(
        days,
        threshold_days=continuity.threshold_days,
        warning_days=continuity.warning_days,
    )
    rule_reasons = [
        threshold_reason(days, severity, continuity.threshold_days, continuity.warning_days)
    ]
    reserve_reasons = protected_reserve_reasons(continuity)
    if reserve_reasons:
        severity = max_severity(severity, "medium")
        rule_reasons.extend(reserve_reasons)
    candidates.append(
        with_explainability(
            RiskCandidate(
                risk_type="days_of_cover_breach",
                severity=severity,
                plant_reference=continuity.plant_reference,
                material_reference=continuity.material_reference,
                days_of_cover=days,
                projected_exhaustion_date=continuity.projected_exhaustion_date,
                rule_reasons=rule_reasons,
                recommended_owner_role="materials_planner",
            )
        )
    )

    stockout_horizon = stockout_alert_horizon(continuity)
    if (
        continuity.projected_exhaustion_date is not None
        and now is not None
        and ensure_utc(continuity.projected_exhaustion_date)
        <= ensure_utc(now) + timedelta(hours=float(stockout_horizon))
    ):
        horizon_reason = (
            f"Projected exhaustion date is within {stockout_horizon_days_label(stockout_horizon)} "
            "stockout alert horizon"
        )
        candidates.append(
            with_explainability(
                RiskCandidate(
                    risk_type="projected_stockout",
                    severity="critical",
                    plant_reference=continuity.plant_reference,
                    material_reference=continuity.material_reference,
                    days_of_cover=days,
                    projected_exhaustion_date=continuity.projected_exhaustion_date,
                    rule_reasons=[
                        horizon_reason,
                        stockout_horizon_source_reason(continuity),
                    ],
                    recommended_owner_role="materials_planner",
                )
            )
        )
    return candidates


def evaluate_shipment_rules(continuity: ShipmentContinuityResult) -> list[RiskCandidate]:
    candidates: list[RiskCandidate] = []
    if continuity.status == "degraded":
        severity = (
            "high"
            if continuity.tracking_freshness_status in {"stale", "critical"}
            or (continuity.eta_slip_days is not None and continuity.eta_slip_days > Decimal("1"))
            else "medium"
        )
        candidates.append(
            with_explainability(
                RiskCandidate(
                    risk_type="shipment_degraded",
                    severity=severity,
                    plant_reference=continuity.linked_plant_reference,
                    material_reference=continuity.linked_material_reference,
                    shipment_reference=continuity.shipment_reference,
                    continuity_status=continuity.status,
                    freshness_status=continuity.tracking_freshness_status,
                    rule_reasons=list(continuity.continuity_reasons),
                    recommended_owner_role="logistics_planner",
                )
            )
        )
    elif continuity.status == "watch":
        candidates.append(
            with_explainability(
                RiskCandidate(
                    risk_type="shipment_degraded",
                    severity="low",
                    plant_reference=continuity.linked_plant_reference,
                    material_reference=continuity.linked_material_reference,
                    shipment_reference=continuity.shipment_reference,
                    continuity_status=continuity.status,
                    freshness_status=continuity.tracking_freshness_status,
                    rule_reasons=list(continuity.continuity_reasons),
                    recommended_owner_role="logistics_planner",
                )
            )
        )

    if missing_context_from_shipment(continuity):
        candidates.append(
            with_explainability(
                RiskCandidate(
                    risk_type="missing_operational_context",
                    severity="low",
                    plant_reference=continuity.linked_plant_reference,
                    material_reference=continuity.linked_material_reference,
                    shipment_reference=continuity.shipment_reference,
                    continuity_status=continuity.status,
                    rule_reasons=["Shipment is missing plant, material, shipment, or PO context"],
                    recommended_owner_role="data_steward",
                )
            )
        )
    return candidates


def evaluate_inbound_delay_against_cover(
    shipment: ShipmentContinuityResult,
    inventory: InventoryContinuityResult,
    *,
    db: Session | None = None,
    tenant_id: int | None = None,
    shipment_model: Shipment | None = None,
    now: datetime | None = None,
) -> list[RiskCandidate]:
    if inventory.days_of_cover is None:
        return []
    result = evaluate_inbound_delay_cover_intelligence(
        shipment,
        inventory,
        db=db,
        tenant_id=tenant_id,
        shipment=shipment_model,
        now=now,
    )
    if not result.applies:
        return []
    return [
        with_explainability(
            RiskCandidate(
                risk_type=result.risk_type,
                severity=result.severity,
                plant_reference=inventory.plant_reference,
                material_reference=inventory.material_reference,
                shipment_reference=shipment.shipment_reference,
                days_of_cover=inventory.days_of_cover,
                projected_exhaustion_date=inventory.projected_exhaustion_date,
                continuity_status=shipment.status,
                freshness_status=shipment.tracking_freshness_status,
                rule_reasons=result.reason_chain,
                recommended_owner_role="logistics_planner",
            )
        )
    ]


def evaluate_event_trust_rules(event: OperationalEvent) -> list[RiskCandidate]:
    candidates: list[RiskCandidate] = []
    freshness = event.freshness_status.value if event.freshness_status is not None else None
    if freshness in {"stale", "critical"}:
        candidates.append(
            with_explainability(
                RiskCandidate(
                    risk_type="stale_signal_risk",
                    severity="high" if freshness == "critical" else "medium",
                    plant_reference=event.plant_reference,
                    material_reference=event.material_reference,
                    shipment_reference=event.shipment_reference,
                    supplier_reference=event.supplier_reference,
                    confidence_score=event.confidence_score,
                    freshness_status=freshness,
                    rule_reasons=[f"Operational event freshness is {freshness}"],
                    source_event_ids=[event.id],
                    recommended_owner_role="data_steward",
                ),
                [event],
            )
        )

    if event.confidence_score is not None and event.confidence_score < Decimal("50"):
        severity = "high" if event.confidence_score < Decimal("30") else "medium"
        candidates.append(
            with_explainability(
                RiskCandidate(
                    risk_type="low_confidence_signal_risk",
                    severity=severity,
                    plant_reference=event.plant_reference,
                    material_reference=event.material_reference,
                    shipment_reference=event.shipment_reference,
                    supplier_reference=event.supplier_reference,
                    confidence_score=event.confidence_score,
                    freshness_status=freshness,
                    rule_reasons=[f"Operational event confidence is {event.confidence_score}"],
                    source_event_ids=[event.id],
                    recommended_owner_role="data_steward",
                ),
                [event],
            )
        )

    if missing_context_from_event(event):
        candidates.append(
            with_explainability(
                RiskCandidate(
                    risk_type="missing_operational_context",
                    severity="low",
                    plant_reference=event.plant_reference,
                    material_reference=event.material_reference,
                    shipment_reference=event.shipment_reference,
                    supplier_reference=event.supplier_reference,
                    confidence_score=event.confidence_score,
                    freshness_status=freshness,
                    rule_reasons=[
                        "Operational event is missing key plant, material, or shipment context"
                    ],
                    source_event_ids=[event.id],
                    recommended_owner_role="data_steward",
                ),
                [event],
            )
        )
    return candidates


def with_explainability(
    candidate: RiskCandidate,
    source_events: list[OperationalEvent] | None = None,
) -> RiskCandidate:
    candidate.explainability = build_explainability(candidate, source_events or [])
    return candidate


def attach_explainability(
    candidates: list[RiskCandidate],
    events: list[OperationalEvent],
) -> list[RiskCandidate]:
    return [
        with_explainability(candidate, matching_source_events(candidate, events))
        for candidate in candidates
    ]


def build_explainability(
    candidate: RiskCandidate,
    source_events: list[OperationalEvent],
) -> RiskExplainability:
    return RiskExplainability(
        summary=summary_for(candidate),
        primary_driver=primary_driver_for(candidate),
        contributing_signals=[signal_from_event(event) for event in source_events],
        operational_context=OperationalContext(
            plant_reference=candidate.plant_reference,
            material_reference=candidate.material_reference,
            shipment_reference=candidate.shipment_reference,
            supplier_reference=candidate.supplier_reference,
            days_of_cover=candidate.days_of_cover,
            projected_exhaustion_date=candidate.projected_exhaustion_date,
            shipment_continuity_status=candidate.continuity_status,
        ),
        trust_context=trust_context_for(candidate, source_events),
        reason_chain=list(candidate.rule_reasons),
    )


def summary_for(candidate: RiskCandidate) -> str:
    plant = candidate.plant_reference or "unknown plant"
    material = candidate.material_reference or "unknown material"
    shipment = candidate.shipment_reference or "unknown shipment"
    if candidate.risk_type == "days_of_cover_breach":
        return (
            f"Material {material} at plant {plant} has {candidate.days_of_cover} "
            "days of cover, below the configured continuity threshold."
        )
    if candidate.risk_type == "projected_stockout":
        return (
            f"Material {material} at plant {plant} is projected to exhaust on "
            f"{candidate.projected_exhaustion_date}."
        )
    if candidate.risk_type == "protected_reserve_breach":
        return (
            f"Material {material} at plant {plant} has breached a protected reserve "
            "continuity threshold."
        )
    if candidate.risk_type == "inbound_delay_against_cover":
        return (
            f"Inbound shipment {shipment} is degraded while available cover is only "
            f"{candidate.days_of_cover} days."
        )
    if candidate.risk_type == "shipment_degraded":
        return (
            f"Shipment {shipment} is degraded due to ETA slip, overdue milestone, "
            "or stale tracking."
        )
    if candidate.risk_type == "stale_signal_risk":
        return (
            "A source signal is stale/critical, reducing trust in current operational visibility."
        )
    if candidate.risk_type == "low_confidence_signal_risk":
        return (
            "A source signal has low confidence, so this operational view may be "
            "incomplete or unreliable."
        )
    if candidate.risk_type == "missing_operational_context":
        return (
            "This signal is missing plant/material/shipment linkage, limiting "
            "continuity interpretation."
        )
    return f"Rule {candidate.risk_type} generated a {candidate.severity} risk candidate."


def primary_driver_for(candidate: RiskCandidate) -> str:
    if candidate.risk_type in {
        "days_of_cover_breach",
        "projected_stockout",
        "protected_reserve_breach",
    }:
        return "inventory_continuity"
    if candidate.risk_type in {"shipment_degraded", "inbound_delay_against_cover"}:
        return "shipment_continuity"
    if candidate.risk_type in {"stale_signal_risk", "low_confidence_signal_risk"}:
        return "signal_trust"
    if candidate.risk_type == "missing_operational_context":
        return "missing_operational_context"
    return candidate.risk_type


def signal_from_event(event: OperationalEvent) -> ContributingSignal:
    freshness = event.freshness_status.value if event.freshness_status is not None else None
    return ContributingSignal(
        signal_type=event.event_type.value,
        event_id=str(event.id),
        source_type=event.source_type.value,
        occurred_at=event.occurred_at,
        confidence_score=event.confidence_score,
        freshness_status=freshness,
        description=(
            f"{event.event_type.value} from {event.source_type.value}"
            f" for {event.plant_reference or event.shipment_reference or 'unlinked context'}"
        ),
    )


def trust_context_for(
    candidate: RiskCandidate,
    source_events: list[OperationalEvent],
) -> TrustContext:
    confidence_values = [
        event.confidence_score for event in source_events if event.confidence_score is not None
    ]
    if candidate.confidence_score is not None:
        confidence_values.append(candidate.confidence_score)
    freshness_values = [
        event.freshness_status.value
        for event in source_events
        if event.freshness_status is not None
    ]
    if candidate.freshness_status is not None:
        freshness_values.append(candidate.freshness_status)
    lowest_confidence = min(confidence_values) if confidence_values else None
    worst_freshness = worst_freshness_status(freshness_values)
    warnings = trust_warnings(candidate, lowest_confidence, worst_freshness)
    return TrustContext(
        lowest_confidence_score=lowest_confidence,
        worst_freshness_status=worst_freshness,
        trust_warnings=warnings,
    )


def trust_warnings(
    candidate: RiskCandidate,
    lowest_confidence: Decimal | None,
    worst_freshness: str | None,
) -> list[str]:
    warnings = []
    if worst_freshness in {"stale", "critical"}:
        if candidate.shipment_reference:
            warnings.append(f"Shipment tracking data is {worst_freshness}")
        else:
            warnings.append(f"Operational signal freshness is {worst_freshness}")
    if lowest_confidence is not None and lowest_confidence < Decimal("50"):
        warnings.append(f"Operational signal confidence is low at {lowest_confidence}")
    return warnings


def worst_freshness_status(values: list[str]) -> str | None:
    if not values:
        return None
    return max(values, key=lambda value: FRESHNESS_ORDER.get(value, 0))


def matching_source_events(
    candidate: RiskCandidate,
    events: list[OperationalEvent],
) -> list[OperationalEvent]:
    if candidate.source_event_ids:
        ids = set(candidate.source_event_ids)
        return sorted((event for event in events if event.id in ids), key=lambda event: event.id)
    matches = [event for event in events if event_matches_candidate_context(event, candidate)]
    return sorted(matches, key=lambda event: event.id)


def event_matches_candidate_context(event: OperationalEvent, candidate: RiskCandidate) -> bool:
    if candidate.shipment_reference and event.shipment_reference == candidate.shipment_reference:
        return True
    if (
        candidate.plant_reference
        and candidate.material_reference
        and event.plant_reference == candidate.plant_reference
        and event.material_reference == candidate.material_reference
    ):
        return True
    return False


def severity_for_days_of_cover(
    days_of_cover: Decimal,
    threshold_days: Decimal | None = None,
    warning_days: Decimal | None = None,
) -> str:
    if threshold_days is not None:
        if days_of_cover <= threshold_days:
            return "critical"
        if warning_days is not None and days_of_cover <= warning_days:
            return "medium"
        return "low"
    if days_of_cover <= Decimal("2"):
        return "critical"
    if days_of_cover <= Decimal("5"):
        return "high"
    if days_of_cover <= Decimal("10"):
        return "medium"
    return "low"


def threshold_reason(
    days_of_cover: Decimal,
    severity: str,
    threshold_days: Decimal | None,
    warning_days: Decimal | None,
) -> str:
    if threshold_days is None:
        return f"Days of cover is {days_of_cover}, mapped to {severity} by default thresholds"
    if days_of_cover <= threshold_days:
        return (
            f"Days of cover is {days_of_cover}, at or below configured critical threshold "
            f"of {threshold_days} days"
        )
    if warning_days is not None and days_of_cover <= warning_days:
        return (
            f"Days of cover is {days_of_cover}, at or below configured warning threshold "
            f"of {warning_days} days"
        )
    return f"Days of cover is {days_of_cover}, above configured warning and critical thresholds"


def protected_reserve_reasons(continuity: InventoryContinuityResult) -> list[str]:
    reasons: list[str] = []
    if (
        continuity.minimum_buffer_stock_days is not None
        and continuity.days_of_cover is not None
        and continuity.days_of_cover <= continuity.minimum_buffer_stock_days
    ):
        reasons.append(
            "Protected reserve days threshold was breached: "
            f"{continuity.days_of_cover} days of cover is at or below "
            f"{continuity.minimum_buffer_stock_days} days."
        )
    if (
        continuity.minimum_buffer_stock_mt is not None
        and continuity.usable_quantity <= continuity.minimum_buffer_stock_mt
    ):
        reasons.append(
            "Protected reserve quantity threshold was breached: "
            f"{continuity.usable_quantity} {continuity.unit} usable is at or below "
            f"{continuity.minimum_buffer_stock_mt} {continuity.unit}."
        )
    return reasons


def protected_reserve_candidate(
    continuity: InventoryContinuityResult,
    reserve_reasons: list[str],
) -> RiskCandidate:
    return with_explainability(
        RiskCandidate(
            risk_type="protected_reserve_breach",
            severity="medium",
            plant_reference=continuity.plant_reference,
            material_reference=continuity.material_reference,
            days_of_cover=continuity.days_of_cover,
            projected_exhaustion_date=continuity.projected_exhaustion_date,
            rule_reasons=reserve_reasons,
            recommended_owner_role="materials_planner",
        )
    )


def stockout_alert_horizon(continuity: InventoryContinuityResult) -> Decimal:
    if continuity.stockout_alert_horizon_days is None:
        return DEFAULT_STOCKOUT_ALERT_HOURS
    return continuity.stockout_alert_horizon_days * Decimal("24")


def stockout_horizon_days_label(horizon_hours: Decimal) -> str:
    if horizon_hours == DEFAULT_STOCKOUT_ALERT_HOURS:
        return "48 hours"
    days = horizon_hours / Decimal("24")
    return f"{days.quantize(Decimal('0.01'))} days"


def stockout_horizon_source_reason(continuity: InventoryContinuityResult) -> str:
    if continuity.stockout_alert_horizon_days is None:
        return "Using fallback projected stockout alert horizon of 48 hours."
    return (
        "Using configured projected stockout alert horizon of "
        f"{continuity.stockout_alert_horizon_days.quantize(Decimal('0.01'))} days."
    )


def max_severity(current: str, minimum: str) -> str:
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return current if order.get(current, 3) <= order.get(minimum, 3) else minimum


def inventory_continuity_items(
    db: Session,
    context: RequestContext,
    *,
    now: datetime,
) -> list[InventoryContinuityResult]:
    snapshots = list(
        db.scalars(select(StockSnapshot).where(StockSnapshot.tenant_id == context.tenant_id))
    )
    keys = {(snapshot.plant_id, snapshot.material_id) for snapshot in snapshots}
    items = []
    for plant_id, material_id in sorted(keys):
        item = calculate_inventory_continuity_for(db, context, plant_id, material_id, now=now)
        if item is not None:
            items.append(item)
    return items


def shipment_continuity_items(
    db: Session,
    context: RequestContext,
    *,
    now: datetime,
) -> list[ShipmentContinuityResult]:
    shipments = list(db.scalars(select(Shipment).where(Shipment.tenant_id == context.tenant_id)))
    items = []
    for shipment in shipments:
        item = calculate_shipment_continuity_for(
            db,
            context,
            shipment.shipment_id,
            now=now,
        )
        if item is not None:
            items.append(item)
    return items


def missing_context_from_shipment(continuity: ShipmentContinuityResult) -> bool:
    return not (
        continuity.shipment_reference
        and continuity.linked_material_reference
        and continuity.linked_plant_reference
        and continuity.linked_purchase_order_reference
    )


def missing_context_from_event(event: OperationalEvent) -> bool:
    if event.shipment_reference and (not event.plant_reference or not event.material_reference):
        return True
    if not event.shipment_reference and (not event.plant_reference or not event.material_reference):
        return True
    return False


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
