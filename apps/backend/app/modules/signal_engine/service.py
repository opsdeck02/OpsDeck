from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ContinuityRiskSnapshot,
    Material,
    OperationalEvent,
    Plant,
    Shipment,
    StockSnapshot,
)
from app.models.enums import OperationalEventCategory
from app.modules.exposure.mapping import (
    ExposureTrustSummary,
    OperationalExposureMapping,
    build_exposure_mapping,
)
from app.modules.impact.engine import determine_urgency_band
from app.modules.impact.production_interruption import (
    ProductionInterruptionInputs,
    calculate_production_interruption_impact,
    get_active_interruption_config,
)
from app.modules.impact.shipment_inbound_trust import get_active_shipment_inbound_trust_config
from app.modules.operational_events.timeline import (
    ContinuityTimelineEntry,
    ContinuityTimelineFilters,
    build_continuity_timeline,
    build_timeline_for_risk_candidate,
)
from app.modules.recommendations.operational_actions import recommend_operational_actions
from app.modules.relationships.graph import (
    OperationalRelationshipGraph,
    build_operational_relationship_graph,
)
from app.modules.risk_snapshots.comparison import classify_snapshot_escalation
from app.modules.risk_snapshots.schemas import RiskEscalationComparison
from app.modules.risk_snapshots.service import (
    create_snapshot_from_risk_candidate,
    risk_fingerprint,
)
from app.modules.rules.engine import (
    FRESHNESS_ORDER,
    RiskCandidate,
    RiskExplainability,
    attach_explainability,
    evaluate_rule_based_risks,
)
from app.modules.shipments.continuity import calculate_shipment_continuity_for
from app.modules.shipments.schemas import ShipmentContinuityResult
from app.modules.shipments.visibility_confidence import (
    calculate_visibility_confidence,
    is_physical_inbound_candidate,
    quantize_decimal,
)
from app.modules.signal_engine.candidate_cache import (
    get_cached_signal_candidates,
    invalidate_signal_candidate_cache,
)
from app.modules.signal_engine.pilot_scenarios import DEMO_DATA_NOTICE, prepare_pilot_scenario
from app.modules.stock.continuity import calculate_inventory_continuity_for
from app.modules.stock.schemas import InventoryContinuityResult
from app.modules.suppliers.reliability_context import (
    calculate_supplier_reliability_context,
    supplier_reliability_modifier,
)
from app.modules.trust.operational import (
    evaluate_configuration_completeness,
    evaluate_risk_operational_trust,
    resolve_plant_material,
)
from app.schemas.context import RequestContext

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class TimelineWindow(BaseModel):
    items: list[ContinuityTimelineEntry]
    limit: int
    offset: int
    total: int


class RiskWorkspaceResponse(BaseModel):
    selected_risk: RiskCandidate | None = None
    explainability: RiskExplainability | None = None
    exposure: OperationalExposureMapping | None = None
    timeline: TimelineWindow
    context_graph: OperationalRelationshipGraph | None = None
    inventory_continuity: list[InventoryContinuityResult]
    shipment_continuity: list[ShipmentContinuityResult]
    trust_summary: ExposureTrustSummary | None = None
    empty: bool
    is_demo_scenario: bool = False
    scenario_key: str | None = None
    scenario_label: str | None = None
    demo_data_notice: str | None = None


class MaterialRiskRollup(BaseModel):
    plant_reference: str | None = None
    material_reference: str | None = None
    highest_severity: str
    exception_count: int
    risk_types: list[str]
    earliest_projected_exhaustion_date: datetime | None = None
    lowest_days_of_cover: Decimal | None = None
    representative_shipment_reference: str | None = None
    last_updated_at: datetime | None = None


class EscalationEvaluationResponse(BaseModel):
    risks: list[RiskCandidate]
    snapshot_time: datetime
    snapshots_recorded: int


def list_signal_risks(
    db: Session,
    context: RequestContext,
    *,
    risk_type: str | None = None,
    plant_reference: str | None = None,
    material_reference: str | None = None,
    shipment_reference: str | None = None,
    severity: str | None = None,
    now: datetime | None = None,
    bypass_cache: bool = False,
) -> list[RiskCandidate]:
    candidates = cached_rule_based_risk_candidates(
        db,
        context,
        now=now,
        bypass_cache=bypass_cache,
    )
    filtered = [
        candidate
        for candidate in candidates
        if candidate_matches_filters(
            candidate,
            risk_type=risk_type,
            plant_reference=plant_reference,
            material_reference=material_reference,
            shipment_reference=shipment_reference,
            severity=severity,
        )
    ]
    return enrich_candidates_with_latest_escalation(
        db,
        context,
        attach_candidate_explainability(db, context, filtered),
    )


def list_material_risk_rollups(
    db: Session,
    context: RequestContext,
    *,
    plant_reference: str | None = None,
    material_reference: str | None = None,
    now: datetime | None = None,
) -> list[MaterialRiskRollup]:
    candidates = [
        candidate
        for candidate in cached_rule_based_risk_candidates(db, context, now=now)
        if candidate_matches_filters(
            candidate,
            plant_reference=plant_reference,
            material_reference=material_reference,
            shipment_reference=None,
            severity=None,
        )
    ]
    grouped: dict[tuple[str | None, str | None], list[RiskCandidate]] = {}
    for candidate in candidates:
        key = (candidate.plant_reference, candidate.material_reference)
        grouped.setdefault(key, []).append(candidate)

    rollups = [
        material_rollup_from_candidates(grouped_candidates)
        for grouped_candidates in grouped.values()
    ]
    return sorted(rollups, key=material_rollup_priority_key)


def cached_rule_based_risk_candidates(
    db: Session,
    context: RequestContext,
    *,
    now: datetime | None = None,
    bypass_cache: bool = False,
) -> list[RiskCandidate]:
    return get_cached_signal_candidates(
        context.tenant_id,
        lambda: evaluate_rule_based_risks(db, context, now=now),
        bypass=bypass_cache or now is not None,
    )


def attach_candidate_explainability(
    db: Session,
    context: RequestContext,
    candidates: list[RiskCandidate],
) -> list[RiskCandidate]:
    events = list(
        db.scalars(select(OperationalEvent).where(OperationalEvent.tenant_id == context.tenant_id))
    )
    return attach_explainability(candidates, events)


def get_risk_workspace(
    db: Session,
    context: RequestContext,
    *,
    scenario: str | None = None,
    risk_type: str | None = None,
    plant_reference: str | None = None,
    material_reference: str | None = None,
    shipment_reference: str | None = None,
    severity: str | None = None,
    timeline_limit: int = 50,
    timeline_offset: int = 0,
    now: datetime | None = None,
) -> RiskWorkspaceResponse:
    scenario_key: str | None = None
    scenario_label: str | None = None
    if scenario is not None:
        scenario_now = now or datetime.now(UTC)
        selection = prepare_pilot_scenario(db, context, scenario, now=scenario_now)
        risk_type = selection.risk_type
        plant_reference = selection.plant_reference
        material_reference = selection.material_reference
        shipment_reference = selection.shipment_reference
        severity = selection.severity
        scenario_key = selection.scenario_key
        scenario_label = selection.scenario_label
        now = scenario_now
        invalidate_signal_candidate_cache(context.tenant_id)

    candidates = list_signal_risks(
        db,
        context,
        risk_type=risk_type,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
        severity=severity,
        now=now,
        bypass_cache=scenario_key is not None,
    )
    selected = select_highest_priority_risk(candidates)
    if selected is None:
        return empty_workspace(
            timeline_limit,
            timeline_offset,
            scenario_key=scenario_key,
            scenario_label=scenario_label,
        )

    resolved_plant_reference = plant_reference or selected.plant_reference
    resolved_material_reference = material_reference or selected.material_reference
    resolved_shipment_reference = shipment_reference or selected.shipment_reference
    exposure = build_exposure_mapping(
        db,
        context,
        plant_reference=resolved_plant_reference,
        material_reference=resolved_material_reference,
        shipment_reference=resolved_shipment_reference,
        risk_candidate=selected,
        now=now,
    )
    timeline_items = build_timeline_for_risk_candidate(db, context, selected)
    context_graph = build_operational_relationship_graph(
        db,
        context,
        plant_reference=resolved_plant_reference,
        material_reference=resolved_material_reference,
        shipment_reference=resolved_shipment_reference,
        risk_candidate=selected,
        now=now,
    )
    inventory_continuity = list_inventory_continuity(
        db,
        context,
        plant_reference=resolved_plant_reference,
        material_reference=resolved_material_reference,
        now=now,
    )
    shipment_continuity = list_shipment_continuity(
        db,
        context,
        plant_reference=resolved_plant_reference,
        material_reference=resolved_material_reference,
        shipment_reference=resolved_shipment_reference,
        inventory=first_or_none(inventory_continuity),
        now=now,
    )
    return RiskWorkspaceResponse(
        selected_risk=selected,
        explainability=selected.explainability,
        exposure=exposure,
        timeline=timeline_window(timeline_items, timeline_limit, timeline_offset),
        context_graph=context_graph,
        inventory_continuity=inventory_continuity,
        shipment_continuity=shipment_continuity,
        trust_summary=exposure.trust_summary,
        empty=False,
        is_demo_scenario=scenario_key is not None,
        scenario_key=scenario_key,
        scenario_label=scenario_label,
        demo_data_notice=DEMO_DATA_NOTICE if scenario_key is not None else None,
    )


def evaluate_and_record_risk_escalation(
    db: Session,
    context: RequestContext,
    *,
    risk_type: str | None = None,
    plant_reference: str | None = None,
    material_reference: str | None = None,
    shipment_reference: str | None = None,
    severity: str | None = None,
    snapshot_time: datetime | None = None,
) -> EscalationEvaluationResponse:
    captured_at = snapshot_time or datetime.now(UTC)
    candidates = [
        candidate
        for candidate in evaluate_rule_based_risks(db, context, now=captured_at)
        if candidate_matches_filters(
            candidate,
            risk_type=risk_type,
            plant_reference=plant_reference,
            material_reference=material_reference,
            shipment_reference=shipment_reference,
            severity=severity,
        )
    ]
    enriched: list[RiskCandidate] = []
    for candidate in candidates:
        resolved_plant_reference = plant_reference or candidate.plant_reference
        resolved_material_reference = material_reference or candidate.material_reference
        resolved_shipment_reference = shipment_reference or candidate.shipment_reference
        exposure = build_exposure_mapping(
            db,
            context,
            plant_reference=resolved_plant_reference,
            material_reference=resolved_material_reference,
            shipment_reference=resolved_shipment_reference,
            risk_candidate=candidate,
            now=captured_at,
        )
        inventory = first_or_none(
            list_inventory_continuity(
                db,
                context,
                plant_reference=resolved_plant_reference,
                material_reference=resolved_material_reference,
                now=captured_at,
            )
        )
        shipment = first_or_none(
            list_shipment_continuity(
                db,
                context,
                plant_reference=resolved_plant_reference,
                material_reference=resolved_material_reference,
                shipment_reference=resolved_shipment_reference,
                now=captured_at,
            )
        )
        snapshot = create_snapshot_from_risk_candidate(
            db,
            context,
            candidate,
            snapshot_time=captured_at,
            exposure=exposure,
            inventory_continuity=inventory,
            shipment_continuity=shipment,
        )
        comparison = classify_snapshot_escalation(db, snapshot, update_snapshot=True)
        enriched.append(
            apply_operational_recommendations(
                db,
                context,
                apply_operational_interruption_impact(
                    db,
                    context,
                    apply_escalation(candidate, comparison),
                ),
                inventory=inventory,
                shipment=shipment,
            )
        )
    db.commit()
    return EscalationEvaluationResponse(
        risks=enriched,
        snapshot_time=captured_at,
        snapshots_recorded=len(enriched),
    )


def empty_workspace(
    timeline_limit: int,
    timeline_offset: int,
    *,
    scenario_key: str | None = None,
    scenario_label: str | None = None,
) -> RiskWorkspaceResponse:
    return RiskWorkspaceResponse(
        selected_risk=None,
        explainability=None,
        exposure=None,
        timeline=TimelineWindow(
            items=[],
            limit=timeline_limit,
            offset=timeline_offset,
            total=0,
        ),
        context_graph=None,
        inventory_continuity=[],
        shipment_continuity=[],
        trust_summary=None,
        empty=True,
        is_demo_scenario=scenario_key is not None,
        scenario_key=scenario_key,
        scenario_label=scenario_label,
        demo_data_notice=DEMO_DATA_NOTICE if scenario_key is not None else None,
    )


def select_highest_priority_risk(candidates: list[RiskCandidate]) -> RiskCandidate | None:
    if not candidates:
        return None
    return sorted(candidates, key=risk_priority_key)[0]


def material_rollup_from_candidates(
    candidates: list[RiskCandidate],
) -> MaterialRiskRollup:
    ordered = sorted(candidates, key=risk_priority_key)
    highest = ordered[0]
    projected_dates = [
        candidate.projected_exhaustion_date
        for candidate in candidates
        if candidate.projected_exhaustion_date is not None
    ]
    cover_values = [
        candidate.days_of_cover
        for candidate in candidates
        if candidate.days_of_cover is not None
    ]
    representative_shipment_reference = next(
        (
            candidate.shipment_reference
            for candidate in ordered
            if candidate.shipment_reference is not None
        ),
        None,
    )
    return MaterialRiskRollup(
        plant_reference=highest.plant_reference,
        material_reference=highest.material_reference,
        highest_severity=highest.severity,
        exception_count=len(candidates),
        risk_types=sorted({candidate.risk_type for candidate in candidates}),
        earliest_projected_exhaustion_date=(
            min(projected_dates) if projected_dates else None
        ),
        lowest_days_of_cover=min(cover_values) if cover_values else None,
        representative_shipment_reference=representative_shipment_reference,
        last_updated_at=None,
    )


def material_rollup_priority_key(rollup: MaterialRiskRollup) -> tuple:
    projected = rollup.earliest_projected_exhaustion_date
    projected_sort = projected.timestamp() if projected is not None else float("inf")
    cover_sort = rollup.lowest_days_of_cover
    return (
        SEVERITY_ORDER.get(rollup.highest_severity, 99),
        -rollup.exception_count,
        projected_sort,
        cover_sort if cover_sort is not None else Decimal("999999999"),
        rollup.plant_reference or "",
        rollup.material_reference or "",
    )


def risk_priority_key(candidate: RiskCandidate) -> tuple:
    projected = candidate.projected_exhaustion_date
    projected_sort = projected.timestamp() if projected is not None else float("inf")
    confidence = candidate.confidence_score
    confidence_sort = confidence if confidence is not None else Decimal("101")
    return (
        SEVERITY_ORDER.get(candidate.severity, 99),
        projected_sort,
        -FRESHNESS_ORDER.get(candidate.freshness_status or "fresh", 0),
        confidence_sort,
        candidate.risk_type,
        candidate.plant_reference or "",
        candidate.material_reference or "",
        candidate.shipment_reference or "",
    )


def timeline_window(
    items: list[ContinuityTimelineEntry],
    limit: int,
    offset: int,
) -> TimelineWindow:
    normalized_limit = max(limit, 0)
    normalized_offset = max(offset, 0)
    return TimelineWindow(
        items=items[normalized_offset : normalized_offset + normalized_limit],
        limit=normalized_limit,
        offset=normalized_offset,
        total=len(items),
    )


def list_signal_exposures(
    db: Session,
    context: RequestContext,
    *,
    plant_reference: str | None = None,
    material_reference: str | None = None,
    shipment_reference: str | None = None,
    exposure_level: str | None = None,
    now: datetime | None = None,
) -> list[OperationalExposureMapping]:
    scopes = exposure_scopes(
        db,
        context,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
    )
    exposures = [
        build_exposure_mapping(
            db,
            context,
            plant_reference=scope["plant_reference"],
            material_reference=scope["material_reference"],
            shipment_reference=scope["shipment_reference"],
            now=now,
        )
        for scope in scopes
    ]
    if exposure_level:
        exposures = [
            exposure for exposure in exposures if exposure.exposure_level == exposure_level
        ]
    return exposures


def list_signal_timeline(
    db: Session,
    context: RequestContext,
    *,
    plant_reference: str | None = None,
    material_reference: str | None = None,
    shipment_reference: str | None = None,
    event_category: OperationalEventCategory | str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[ContinuityTimelineEntry]:
    return build_continuity_timeline(
        db,
        context,
        filters=ContinuityTimelineFilters(
            plant_reference=plant_reference,
            material_reference=material_reference,
            shipment_reference=shipment_reference,
            event_category=event_category,
            since=since,
            until=until,
        ),
    )


def get_signal_context_graph(
    db: Session,
    context: RequestContext,
    *,
    plant_reference: str | None = None,
    material_reference: str | None = None,
    shipment_reference: str | None = None,
    now: datetime | None = None,
) -> OperationalRelationshipGraph:
    return build_operational_relationship_graph(
        db,
        context,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
        now=now,
    )


def list_inventory_continuity(
    db: Session,
    context: RequestContext,
    *,
    plant_reference: str | None = None,
    material_reference: str | None = None,
    now: datetime | None = None,
) -> list[InventoryContinuityResult]:
    items = []
    for plant_id, material_id in inventory_keys(db, context):
        plant = db.get(Plant, plant_id)
        material = db.get(Material, material_id)
        if plant is None or material is None:
            continue
        if plant.tenant_id != context.tenant_id or material.tenant_id != context.tenant_id:
            continue
        if plant_reference and plant.code != plant_reference:
            continue
        if material_reference and material.code != material_reference:
            continue
        continuity = calculate_inventory_continuity_for(
            db,
            context,
            plant_id,
            material_id,
            now=now,
        )
        if continuity is not None:
            items.append(continuity)
    return sorted(
        items,
        key=lambda item: (item.plant_reference, item.material_reference),
    )


def list_shipment_continuity(
    db: Session,
    context: RequestContext,
    *,
    plant_reference: str | None = None,
    material_reference: str | None = None,
    shipment_reference: str | None = None,
    inventory: InventoryContinuityResult | None = None,
    now: datetime | None = None,
) -> list[ShipmentContinuityResult]:
    items = []
    shipments = db.scalars(select(Shipment).where(Shipment.tenant_id == context.tenant_id))
    for shipment in shipments:
        if shipment_reference and shipment.shipment_id != shipment_reference:
            continue
        continuity = calculate_shipment_continuity_for(
            db,
            context,
            shipment.shipment_id,
            now=now,
        )
        if continuity is None:
            continue
        if plant_reference and continuity.linked_plant_reference != plant_reference:
            continue
        if material_reference and continuity.linked_material_reference != material_reference:
            continue
        items.append(
            enrich_shipment_protection(
                db,
                context,
                shipment,
                continuity,
                inventory=inventory,
                now=now,
            )
        )
    return sorted(items, key=lambda item: item.shipment_reference)


def enrich_shipment_protection(
    db: Session,
    context: RequestContext,
    shipment: Shipment,
    continuity: ShipmentContinuityResult,
    *,
    inventory: InventoryContinuityResult | None,
    now: datetime | None = None,
) -> ShipmentContinuityResult:
    if shipment.plant_id is None or shipment.material_id is None:
        return continuity.model_copy(
            update={
                "physical_quantity": shipment.quantity_mt,
                "trusted_quantity": None,
                "protective_quantity": None,
                "protective_value_label": "Unknown protection",
                "trust_level": "unknown",
                "trust_reason": "Shipment is missing plant or material linkage.",
                "freshness_status": continuity.tracking_freshness_status,
                "movement_condition": continuity.status,
                "eta_status": "unknown",
                "eta_drift_days": continuity.eta_slip_days,
                "is_currently_protective": None,
                "protection_explanation": (
                    "Precise protection is unavailable because plant/material linkage is missing."
                ),
            }
        )
    if not is_physical_inbound_candidate(shipment):
        return continuity.model_copy(
            update={
                "physical_quantity": shipment.quantity_mt,
                "trusted_quantity": Decimal("0.00"),
                "protective_quantity": Decimal("0.00"),
                "protective_value_label": "Not currently protective",
                "trust_level": "not_protective",
                "trust_reason": "Shipment state is not eligible for physical inbound protection.",
                "freshness_status": continuity.tracking_freshness_status,
                "movement_condition": continuity.status,
                "eta_status": eta_status_for(continuity),
                "eta_drift_days": continuity.eta_slip_days,
                "is_currently_protective": False,
                "protection_explanation": (
                    "Inbound exists in records, but this movement state is not currently "
                    "protective for continuity cover."
                ),
            }
        )

    trust_config = get_active_shipment_inbound_trust_config(
        db,
        tenant_id=context.tenant_id,
        plant_id=shipment.plant_id,
        material_id=shipment.material_id,
    )
    visibility = calculate_visibility_confidence(
        shipment,
        now=now,
        trust_config=trust_config,
    )
    supplier = calculate_supplier_reliability_context(
        db,
        tenant_id=context.tenant_id,
        shipment=shipment,
        visibility_result=visibility,
        now=now,
    )
    adjusted_confidence = max(
        Decimal("0.00"),
        min(
            Decimal("1.00"),
            visibility.visibility_confidence
            + supplier_reliability_modifier(supplier.reliability_band),
        ),
    )
    physical = visibility.physical_inbound_quantity_mt
    trusted = quantize_decimal(physical * adjusted_confidence)
    arrives_before_cover_loss = arrives_before_projected_exhaustion(shipment, inventory)
    label, trust_level, is_protective, reason = protection_status(
        continuity,
        adjusted_confidence=adjusted_confidence,
        arrives_before_cover_loss=arrives_before_cover_loss,
    )
    protective_quantity = trusted if is_protective else Decimal("0.00")
    explanation = protection_explanation(
        shipment,
        continuity,
        label=label,
        trust_reason=reason,
        arrives_before_cover_loss=arrives_before_cover_loss,
        trusted=trusted,
    )

    return continuity.model_copy(
        update={
            "physical_quantity": physical,
            "trusted_quantity": trusted,
            "protective_quantity": protective_quantity,
            "protective_value_label": label,
            "trust_level": trust_level,
            "trust_reason": reason,
            "freshness_status": continuity.tracking_freshness_status,
            "movement_condition": continuity.status,
            "eta_status": visibility.eta_behavior_status,
            "eta_drift_days": continuity.eta_slip_days,
            "is_currently_protective": is_protective,
            "protection_explanation": explanation,
        }
    )


def arrives_before_projected_exhaustion(
    shipment: Shipment,
    inventory: InventoryContinuityResult | None,
) -> bool | None:
    if (
        shipment.current_eta is None
        or inventory is None
        or inventory.projected_exhaustion_date is None
    ):
        return None
    return ensure_utc(shipment.current_eta) <= ensure_utc(inventory.projected_exhaustion_date)


def protection_status(
    continuity: ShipmentContinuityResult,
    *,
    adjusted_confidence: Decimal,
    arrives_before_cover_loss: bool | None,
) -> tuple[str, str, bool | None, str]:
    if arrives_before_cover_loss is False:
        return (
            "Not currently protective",
            "not_protective",
            False,
            "Inbound ETA is after projected cover loss.",
        )
    if continuity.eta is None:
        return (
            "Unknown protection",
            "unknown",
            None,
            "Current ETA is missing, so protection timing cannot be confirmed.",
        )
    if continuity.status == "degraded" or continuity.tracking_freshness_status == "critical":
        return (
            "Weak protection",
            "weak",
            adjusted_confidence > Decimal("0"),
            "Movement condition, ETA, or visibility freshness is degraded.",
        )
    if adjusted_confidence >= Decimal("0.80") and arrives_before_cover_loss is not False:
        return (
            "Strong protection",
            "strong",
            True,
            "Inbound quantity exists, visibility is acceptable, and ETA protects cover.",
        )
    if adjusted_confidence >= Decimal("0.40"):
        return (
            "Partial protection",
            "partial",
            True,
            "Inbound helps protect cover, but ETA, freshness, or confidence is imperfect.",
        )
    return (
        "Weak protection",
        "weak",
        adjusted_confidence > Decimal("0"),
        "Inbound exists physically, but confidence is too weak for strong protection.",
    )


def eta_status_for(continuity: ShipmentContinuityResult) -> str:
    if continuity.eta is None:
        return "unknown"
    if continuity.eta_slip_days is None:
        return "unknown"
    if continuity.eta_slip_days <= 0:
        return "stable"
    if continuity.eta_slip_days <= Decimal("1"):
        return "drifting"
    return "degraded"


def protection_explanation(
    shipment: Shipment,
    continuity: ShipmentContinuityResult,
    *,
    label: str,
    trust_reason: str,
    arrives_before_cover_loss: bool | None,
    trusted: Decimal,
) -> str:
    movement = shipment.current_milestone or continuity.status
    if label == "Strong protection":
        return (
            f"Inbound {shipment.shipment_id} provides strong protection: ETA is before "
            f"projected cover loss and {trusted} MT is trusted for continuity cover."
        )
    if label == "Partial protection":
        return (
            f"Inbound {shipment.shipment_id} provides partial protection: {trust_reason}"
        )
    if label == "Weak protection":
        return (
            f"Inbound {shipment.shipment_id} is weak protection: {trust_reason}"
        )
    if label == "Not currently protective":
        timing = (
            " ETA is after projected cover loss."
            if arrives_before_cover_loss is False
            else ""
        )
        return (
            f"Inbound {shipment.shipment_id} is not currently protective: "
            f"{movement} is not reliable for continuity cover.{timing}"
        )
    return (
        f"Inbound {shipment.shipment_id} has unknown protection: {trust_reason}"
    )


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def enrich_candidates_with_latest_escalation(
    db: Session,
    context: RequestContext,
    candidates: list[RiskCandidate],
) -> list[RiskCandidate]:
    return [
        apply_operational_recommendations(
            db,
            context,
            apply_operational_trust(
                db,
                context,
                apply_operational_interruption_impact(
                    db,
                    context,
                    apply_snapshot_escalation(
                        candidate,
                        escalation_for_snapshot(
                            db,
                            latest_snapshot_for_candidate(db, context, candidate),
                        ),
                    ),
                ),
            ),
        )
        for candidate in candidates
    ]


def latest_snapshot_for_candidate(
    db: Session,
    context: RequestContext,
    candidate: RiskCandidate,
) -> ContinuityRiskSnapshot | None:
    fingerprint = risk_fingerprint(
        tenant_id=context.tenant_id,
        risk_type=candidate.risk_type,
        plant_reference=candidate.plant_reference,
        material_reference=candidate.material_reference,
        shipment_reference=candidate.shipment_reference,
    )
    return db.scalar(
        select(ContinuityRiskSnapshot)
        .where(
            ContinuityRiskSnapshot.tenant_id == context.tenant_id,
            ContinuityRiskSnapshot.risk_fingerprint == fingerprint,
        )
        .order_by(ContinuityRiskSnapshot.snapshot_time.desc())
        .limit(1)
    )


def apply_snapshot_escalation(
    candidate: RiskCandidate,
    comparison: RiskEscalationComparison | None,
) -> RiskCandidate:
    if comparison is None:
        return candidate
    return apply_escalation(candidate, comparison)


def apply_operational_interruption_impact(
    db: Session,
    context: RequestContext,
    candidate: RiskCandidate,
) -> RiskCandidate:
    if candidate.plant_reference is None or candidate.material_reference is None:
        return candidate
    plant = db.scalar(
        select(Plant).where(
            Plant.tenant_id == context.tenant_id,
            Plant.code == candidate.plant_reference,
        )
    )
    material = db.scalar(
        select(Material).where(
            Material.tenant_id == context.tenant_id,
            Material.code == candidate.material_reference,
        )
    )
    if plant is None or material is None:
        return candidate
    risk_hours = (
        candidate.days_of_cover * Decimal("24") if candidate.days_of_cover is not None else None
    )
    urgency = determine_urgency_band(
        candidate.continuity_status or candidate.severity,
        candidate.days_of_cover,
        risk_hours,
    )
    operational_impact = calculate_production_interruption_impact(
        ProductionInterruptionInputs(
            tenant_id=context.tenant_id,
            plant_id=plant.id,
            material_id=material.id,
            material_exposure_value=None,
            days_of_cover=candidate.days_of_cover,
            risk_hours_remaining=risk_hours,
            urgency_band=urgency,
            continuity_severity=candidate.severity,
            projected_exhaustion_date=candidate.projected_exhaustion_date,
            freshness_status=candidate.freshness_status,
        ),
        get_active_interruption_config(
            db,
            tenant_id=context.tenant_id,
            plant_id=plant.id,
            material_id=material.id,
        ),
        db=db,
    )
    return candidate.model_copy(update={"operational_interruption_impact": operational_impact})


def apply_operational_recommendations(
    db: Session,
    context: RequestContext,
    candidate: RiskCandidate,
    *,
    inventory: InventoryContinuityResult | None = None,
    shipment: ShipmentContinuityResult | None = None,
) -> RiskCandidate:
    resolved_inventory = inventory or first_or_none(
        list_inventory_continuity(
            db,
            context,
            plant_reference=candidate.plant_reference,
            material_reference=candidate.material_reference,
        )
    )
    resolved_shipment = shipment or first_or_none(
        list_shipment_continuity(
            db,
            context,
            plant_reference=candidate.plant_reference,
            material_reference=candidate.material_reference,
            shipment_reference=candidate.shipment_reference,
        )
    )
    return candidate.model_copy(
        update={
            "operational_recommendations": recommend_operational_actions(
                candidate,
                inventory=resolved_inventory,
                shipment=resolved_shipment,
            )
        }
    )


def apply_operational_trust(
    db: Session,
    context: RequestContext,
    candidate: RiskCandidate,
) -> RiskCandidate:
    plant, material = resolve_plant_material(
        db,
        tenant_id=context.tenant_id,
        plant_reference=candidate.plant_reference,
        material_reference=candidate.material_reference,
    )
    if plant is None or material is None:
        return candidate
    inventory = first_or_none(
        list_inventory_continuity(
            db,
            context,
            plant_reference=candidate.plant_reference,
            material_reference=candidate.material_reference,
        )
    )
    completeness = evaluate_configuration_completeness(
        db,
        tenant_id=context.tenant_id,
        plant_id=plant.id,
        material_id=material.id,
        inventory=inventory,
    )
    operational_trust = evaluate_risk_operational_trust(
        candidate,
        completeness,
        inventory=inventory,
    )
    updated = candidate.model_copy(
        update={
            "configuration_completeness": completeness,
            "operational_trust": operational_trust,
        }
    )
    if updated.explainability is not None:
        updated.explainability.reason_chain.extend(
            [
                (
                    "Operational trust score is "
                    f"{operational_trust.operational_trust_score}, mapped to "
                    f"{operational_trust.risk_precision_band}."
                ),
                *operational_trust.trust_penalties,
                *operational_trust.trust_boosts,
            ]
        )
    return updated


def escalation_for_snapshot(
    db: Session,
    snapshot: ContinuityRiskSnapshot | None,
) -> RiskEscalationComparison | None:
    if snapshot is None or snapshot.escalation_state is None:
        return None
    return classify_snapshot_escalation(db, snapshot, update_snapshot=False)


def apply_escalation(
    candidate: RiskCandidate,
    comparison: RiskEscalationComparison,
) -> RiskCandidate:
    return candidate.model_copy(update=comparison.model_dump())


def first_or_none(items: list):
    return items[0] if items else None


def exposure_scopes(
    db: Session,
    context: RequestContext,
    *,
    plant_reference: str | None,
    material_reference: str | None,
    shipment_reference: str | None,
) -> list[dict[str, str | None]]:
    if shipment_reference or plant_reference or material_reference:
        return [
            {
                "plant_reference": plant_reference,
                "material_reference": material_reference,
                "shipment_reference": shipment_reference,
            }
        ]

    scopes: dict[tuple[str | None, str | None, str | None], dict[str, str | None]] = {}
    for item in list_inventory_continuity(db, context):
        key = (item.plant_reference, item.material_reference, None)
        scopes[key] = {
            "plant_reference": item.plant_reference,
            "material_reference": item.material_reference,
            "shipment_reference": None,
        }
    for item in list_shipment_continuity(db, context):
        key = (
            item.linked_plant_reference,
            item.linked_material_reference,
            item.shipment_reference,
        )
        scopes[key] = {
            "plant_reference": item.linked_plant_reference,
            "material_reference": item.linked_material_reference,
            "shipment_reference": item.shipment_reference,
        }
    return [scopes[key] for key in sorted(scopes)]


def inventory_keys(db: Session, context: RequestContext) -> set[tuple[int, int]]:
    snapshots = db.scalars(
        select(StockSnapshot).where(StockSnapshot.tenant_id == context.tenant_id)
    )
    return {(snapshot.plant_id, snapshot.material_id) for snapshot in snapshots}


def candidate_matches_filters(
    candidate: RiskCandidate,
    *,
    risk_type: str | None = None,
    plant_reference: str | None,
    material_reference: str | None,
    shipment_reference: str | None,
    severity: str | None,
) -> bool:
    if risk_type and candidate.risk_type != risk_type:
        return False
    if severity and candidate.severity != severity:
        return False
    if plant_reference and candidate.plant_reference != plant_reference:
        return False
    if material_reference and candidate.material_reference != material_reference:
        return False
    if shipment_reference and candidate.shipment_reference != shipment_reference:
        return False
    return True
