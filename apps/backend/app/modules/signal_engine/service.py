from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, Plant, Shipment, StockSnapshot
from app.models.enums import OperationalEventCategory
from app.modules.exposure.mapping import (
    ExposureTrustSummary,
    OperationalExposureMapping,
    build_exposure_mapping,
)
from app.modules.operational_events.timeline import (
    ContinuityTimelineEntry,
    ContinuityTimelineFilters,
    build_continuity_timeline,
    build_timeline_for_risk_candidate,
)
from app.modules.relationships.graph import (
    OperationalRelationshipGraph,
    build_operational_relationship_graph,
)
from app.modules.rules.engine import (
    FRESHNESS_ORDER,
    RiskCandidate,
    RiskExplainability,
    evaluate_rule_based_risks,
)
from app.modules.shipments.continuity import calculate_shipment_continuity_for
from app.modules.shipments.schemas import ShipmentContinuityResult
from app.modules.stock.continuity import calculate_inventory_continuity_for
from app.modules.stock.schemas import InventoryContinuityResult
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
) -> list[RiskCandidate]:
    candidates = evaluate_rule_based_risks(db, context, now=now)
    return [
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


def get_risk_workspace(
    db: Session,
    context: RequestContext,
    *,
    risk_type: str | None = None,
    plant_reference: str | None = None,
    material_reference: str | None = None,
    shipment_reference: str | None = None,
    severity: str | None = None,
    timeline_limit: int = 50,
    timeline_offset: int = 0,
    now: datetime | None = None,
) -> RiskWorkspaceResponse:
    candidates = list_signal_risks(
        db,
        context,
        risk_type=risk_type,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
        severity=severity,
        now=now,
    )
    selected = select_highest_priority_risk(candidates)
    if selected is None:
        return empty_workspace(timeline_limit, timeline_offset)

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
    )


def empty_workspace(timeline_limit: int, timeline_offset: int) -> RiskWorkspaceResponse:
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
    )


def select_highest_priority_risk(candidates: list[RiskCandidate]) -> RiskCandidate | None:
    if not candidates:
        return None
    return sorted(candidates, key=risk_priority_key)[0]


def risk_priority_key(candidate: RiskCandidate) -> tuple:
    projected = candidate.projected_exhaustion_date
    projected_sort = (
        projected.timestamp() if projected is not None else float("inf")
    )
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
            exposure
            for exposure in exposures
            if exposure.exposure_level == exposure_level
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
    now: datetime | None = None,
) -> list[ShipmentContinuityResult]:
    items = []
    shipments = db.scalars(
        select(Shipment).where(Shipment.tenant_id == context.tenant_id)
    )
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
        items.append(continuity)
    return sorted(items, key=lambda item: item.shipment_reference)


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
