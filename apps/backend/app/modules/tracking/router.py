from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_request_context, require_operator_access
from app.modules.tracking.providers import (
    TrackingProviderConfigurationError,
    TrackingProviderRequestError,
)
from app.modules.tracking.schemas import (
    CarrierDetection,
    ContainerSearchRequest,
    ContainerSearchResponse,
    LinkContainerRequest,
    LinkedShipmentStatus,
    ShipmentOption,
    VesselPositionOut,
)
from app.modules.tracking.service import (
    detect_carrier,
    link_container_to_shipment,
    list_shipment_options,
    search_container,
)
from app.modules.tracking.vessel_providers import get_vessel_tracking_provider
from app.schemas.context import RequestContext

router = APIRouter(prefix="/tracking", tags=["tracking"])


@router.get("/carriers/{container_no}", response_model=CarrierDetection)
def detect_container_carrier(container_no: str) -> CarrierDetection:
    try:
        return detect_carrier(container_no)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/containers/search", response_model=ContainerSearchResponse)
def search_tracking_container(
    payload: ContainerSearchRequest,
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> ContainerSearchResponse:
    try:
        result = search_container(
            payload.container_no,
            payload.carrier_code,
            payload.tracking_source,
            db=db,
            context=context,
        )
        db.commit()
        return result
    except TrackingProviderConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "tracking_provider_not_configured", "message": str(exc)},
        ) from exc
    except TrackingProviderRequestError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "tracking_provider_request_failed", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/shipments", response_model=list[ShipmentOption])
def tracking_shipment_options(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ShipmentOption]:
    return list_shipment_options(db, context)


@router.get("/vessels/position", response_model=VesselPositionOut | None)
def vessel_position(
    vessel_name: str,
    _: Annotated[RequestContext, Depends(require_operator_access)],
) -> VesselPositionOut | None:
    provider = get_vessel_tracking_provider()
    return provider.get_vessel_position(vessel_name)


@router.post("/containers/link", response_model=LinkedShipmentStatus)
def link_tracking_container(
    payload: LinkContainerRequest,
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> LinkedShipmentStatus:
    try:
        return link_container_to_shipment(
            db,
            context,
            container_no=payload.container_no,
            carrier_code=payload.carrier_code,
            shipment_id=payload.shipment_id,
            tracking_source=payload.tracking_source,
        )
    except TrackingProviderConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "tracking_provider_not_configured", "message": str(exc)},
        ) from exc
    except TrackingProviderRequestError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "tracking_provider_request_failed", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
