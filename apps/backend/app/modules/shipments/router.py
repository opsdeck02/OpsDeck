from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_request_context, require_roles
from app.modules.auth.constants import (
    LOGISTICS_USER,
    PLANNER_USER,
    SPONSOR_USER,
    TENANT_ADMIN,
)
from app.modules.shipments.movement import (
    get_movement_detail,
    list_inland_monitoring,
    list_port_monitoring,
)
from app.modules.shipments.schemas import (
    InlandMonitoringItem,
    MovementDetailResponse,
    PortMonitoringItem,
    ShipmentDetailResponse,
    ShipmentListItem,
)
from app.modules.shipments.service import (
    VISIBLE_STATES,
    get_shipment_detail,
)
from app.modules.shipments.service import (
    list_shipments as build_shipment_list,
)
from app.schemas.context import RequestContext

router = APIRouter(prefix="/shipments", tags=["shipments"])


@router.get("", response_model=list[ShipmentListItem])
def list_shipments(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ShipmentListItem]:
    return list_shipments_service(db, context)


def list_shipments_service(
    db: Session,
    context: RequestContext,
    plant_id: int | None = None,
    material_id: int | None = None,
    state: str | None = None,
    search: str | None = None,
) -> list[ShipmentListItem]:
    if state and state not in VISIBLE_STATES:
        raise HTTPException(status_code=400, detail="Unsupported shipment state filter")
    return build_shipment_list(
        db=db,
        context=context,
        plant_id=plant_id,
        material_id=material_id,
        state=state,
        search=search,
    )


@router.get("/visibility", response_model=list[ShipmentListItem])
def shipment_visibility(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
    plant_id: Annotated[int | None, Query()] = None,
    material_id: Annotated[int | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
) -> list[ShipmentListItem]:
    return list_shipments_service(db, context, plant_id, material_id, state, search)


@router.get("/port-monitoring", response_model=list[PortMonitoringItem])
def port_monitoring(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
    plant_id: Annotated[int | None, Query()] = None,
    material_id: Annotated[int | None, Query()] = None,
    shipment_id: Annotated[str | None, Query()] = None,
    confidence: Annotated[str | None, Query()] = None,
    delayed_only: Annotated[bool | None, Query()] = None,
) -> list[PortMonitoringItem]:
    return list_port_monitoring(
        db,
        context,
        plant_id=plant_id,
        material_id=material_id,
        shipment_id=shipment_id,
        confidence=confidence,
        delayed_only=delayed_only,
    )


@router.get("/inland-monitoring", response_model=list[InlandMonitoringItem])
def inland_monitoring(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
    plant_id: Annotated[int | None, Query()] = None,
    material_id: Annotated[int | None, Query()] = None,
    shipment_id: Annotated[str | None, Query()] = None,
    confidence: Annotated[str | None, Query()] = None,
    delayed_only: Annotated[bool | None, Query()] = None,
) -> list[InlandMonitoringItem]:
    return list_inland_monitoring(
        db,
        context,
        plant_id=plant_id,
        material_id=material_id,
        shipment_id=shipment_id,
        confidence=confidence,
        delayed_only=delayed_only,
    )


@router.get("/{shipment_id}/movement", response_model=MovementDetailResponse)
def movement_detail(
    shipment_id: str,
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> MovementDetailResponse:
    shipment_items = build_shipment_list(db=db, context=context, search=shipment_id)
    shipment_item = next((item for item in shipment_items if item.shipment_id == shipment_id), None)
    if shipment_item is None:
        raise HTTPException(status_code=404, detail="Shipment not found")
    detail = get_movement_detail(db, context, shipment_id, shipment_item)
    if detail is None:
        raise HTTPException(status_code=404, detail="Shipment movement not found")
    return detail


@router.get("/{shipment_id}", response_model=ShipmentDetailResponse)
def shipment_detail(
    shipment_id: str,
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> ShipmentDetailResponse:
    detail = get_shipment_detail(db, context, shipment_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return detail


@router.post("/sync", dependencies=[Depends(require_roles(TENANT_ADMIN, LOGISTICS_USER))])
def sync_shipments() -> dict[str, str]:
    return {"status": "queued"}


@router.get(
    "/navigation-preview",
    dependencies=[Depends(require_roles(TENANT_ADMIN, PLANNER_USER, SPONSOR_USER))],
)
def navigation_preview() -> list[dict[str, str]]:
    return [
        {"section": "shipments", "access": "read"},
    ]
