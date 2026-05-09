from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_request_context
from app.models.enums import OperationalEventCategory
from app.modules.exposure.mapping import OperationalExposureMapping
from app.modules.operational_events.timeline import ContinuityTimelineEntry
from app.modules.relationships.graph import OperationalRelationshipGraph
from app.modules.rules.engine import RiskCandidate
from app.modules.shipments.schemas import ShipmentContinuityResult
from app.modules.signal_engine.service import (
    RiskWorkspaceResponse,
    get_risk_workspace,
    get_signal_context_graph,
    list_inventory_continuity,
    list_shipment_continuity,
    list_signal_exposures,
    list_signal_risks,
    list_signal_timeline,
)
from app.modules.stock.schemas import InventoryContinuityResult
from app.schemas.context import RequestContext

router = APIRouter(prefix="/signal-engine", tags=["signal-engine"])


@router.get("/risk-workspace", response_model=RiskWorkspaceResponse)
def signal_risk_workspace(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
    risk_type: Annotated[str | None, Query()] = None,
    plant_reference: Annotated[str | None, Query()] = None,
    material_reference: Annotated[str | None, Query()] = None,
    shipment_reference: Annotated[str | None, Query()] = None,
    severity: Annotated[str | None, Query()] = None,
    timeline_limit: Annotated[int, Query(ge=0, le=200)] = 50,
    timeline_offset: Annotated[int, Query(ge=0)] = 0,
) -> RiskWorkspaceResponse:
    return get_risk_workspace(
        db,
        context,
        risk_type=risk_type,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
        severity=severity,
        timeline_limit=timeline_limit,
        timeline_offset=timeline_offset,
    )


@router.get("/risks", response_model=list[RiskCandidate])
def signal_risks(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
    risk_type: Annotated[str | None, Query()] = None,
    plant_reference: Annotated[str | None, Query()] = None,
    material_reference: Annotated[str | None, Query()] = None,
    shipment_reference: Annotated[str | None, Query()] = None,
    severity: Annotated[str | None, Query()] = None,
) -> list[RiskCandidate]:
    return list_signal_risks(
        db,
        context,
        risk_type=risk_type,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
        severity=severity,
    )


@router.get("/exposure", response_model=list[OperationalExposureMapping])
def signal_exposure(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
    plant_reference: Annotated[str | None, Query()] = None,
    material_reference: Annotated[str | None, Query()] = None,
    shipment_reference: Annotated[str | None, Query()] = None,
    exposure_level: Annotated[str | None, Query()] = None,
) -> list[OperationalExposureMapping]:
    return list_signal_exposures(
        db,
        context,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
        exposure_level=exposure_level,
    )


@router.get("/timeline", response_model=list[ContinuityTimelineEntry])
def signal_timeline(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
    plant_reference: Annotated[str | None, Query()] = None,
    material_reference: Annotated[str | None, Query()] = None,
    shipment_reference: Annotated[str | None, Query()] = None,
    event_category: Annotated[OperationalEventCategory | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
) -> list[ContinuityTimelineEntry]:
    return list_signal_timeline(
        db,
        context,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
        event_category=event_category,
        since=since,
        until=until,
    )


@router.get("/context-graph", response_model=OperationalRelationshipGraph)
def signal_context_graph(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
    plant_reference: Annotated[str | None, Query()] = None,
    material_reference: Annotated[str | None, Query()] = None,
    shipment_reference: Annotated[str | None, Query()] = None,
) -> OperationalRelationshipGraph:
    return get_signal_context_graph(
        db,
        context,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
    )


@router.get("/inventory-continuity", response_model=list[InventoryContinuityResult])
def signal_inventory_continuity(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
    plant_reference: Annotated[str | None, Query()] = None,
    material_reference: Annotated[str | None, Query()] = None,
) -> list[InventoryContinuityResult]:
    return list_inventory_continuity(
        db,
        context,
        plant_reference=plant_reference,
        material_reference=material_reference,
    )


@router.get("/shipment-continuity", response_model=list[ShipmentContinuityResult])
def signal_shipment_continuity(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
    plant_reference: Annotated[str | None, Query()] = None,
    material_reference: Annotated[str | None, Query()] = None,
    shipment_reference: Annotated[str | None, Query()] = None,
) -> list[ShipmentContinuityResult]:
    return list_shipment_continuity(
        db,
        context,
        plant_reference=plant_reference,
        material_reference=material_reference,
        shipment_reference=shipment_reference,
    )
