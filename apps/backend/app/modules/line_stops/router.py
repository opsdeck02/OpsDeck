from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_request_context, require_operator_access
from app.modules.line_stops.schemas import (
    LineStopIncidentCreate,
    LineStopIncidentListResponse,
    LineStopIncidentOut,
)
from app.modules.line_stops.service import (
    create_line_stop_incident,
    list_line_stop_incidents,
)
from app.schemas.context import RequestContext

router = APIRouter(prefix="/line-stops", tags=["line-stops"])


@router.get("", response_model=LineStopIncidentListResponse)
def list_incidents(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> LineStopIncidentListResponse:
    return list_line_stop_incidents(db, context, limit=limit)


@router.post("", response_model=LineStopIncidentOut)
def create_incident(
    payload: LineStopIncidentCreate,
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> LineStopIncidentOut:
    try:
        return create_line_stop_incident(db, context, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
