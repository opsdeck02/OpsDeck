from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_request_context, require_operator_access
from app.modules.exceptions.schemas import (
    ExceptionActionRequest,
    ExceptionAssignmentRequest,
    ExceptionCommentOut,
    ExceptionCommentRequest,
    ExceptionDetailResponse,
    ExceptionEvaluationResponse,
    ExceptionListItem,
    ExceptionListResponse,
    ExceptionStatusRequest,
)
from app.modules.exceptions.service import (
    VALID_TRIGGER_TYPES,
    add_exception_comment,
    api_status,
    assign_exception_owner,
    count_resolved_recently,
    detail_context_notes,
    evaluate_exceptions,
    get_exception_detail,
    linked_shipment_detail,
    list_comments,
    serialize_exception,
    update_exception_action_status,
    update_exception_status,
)
from app.modules.exceptions.service import (
    list_exceptions as list_exception_records,
)
from app.schemas.context import RequestContext
from app.utils.csv_exports import build_csv_response

router = APIRouter(prefix="/exceptions", tags=["exceptions"])


@router.get("", response_model=ExceptionListResponse)
def list_exceptions(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    severity: Annotated[str | None, Query()] = None,
    type: Annotated[str | None, Query()] = None,
    plant_id: Annotated[int | None, Query()] = None,
    material_id: Annotated[int | None, Query()] = None,
    shipment_id: Annotated[str | None, Query()] = None,
    owner_user_id: Annotated[int | None, Query()] = None,
    unassigned_only: Annotated[bool, Query()] = False,
) -> ExceptionListResponse:
    if severity and severity not in {"low", "medium", "high", "critical"}:
        raise HTTPException(status_code=400, detail="Unsupported exception severity filter")
    if type and type not in VALID_TRIGGER_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported exception type filter")

    all_items, _ = list_exception_records(db, context)
    items, _ = list_exception_records(
        db,
        context,
        status=status_filter,
        severity=severity,
        type=type,
        plant_id=plant_id,
        material_id=material_id,
        shipment_id=shipment_id,
        owner_user_id=owner_user_id,
        unassigned_only=unassigned_only,
    )
    serialized = [serialize_exception(db, context, item) for item in items]
    return ExceptionListResponse(
        counts={
            "open_exceptions": sum(
                1
                for item in all_items
                if api_status(item.status) in {"open", "in_progress"}
            ),
            "critical_exceptions": sum(
                1 for item in all_items if item.severity.value == "critical"
            ),
            "unassigned_exceptions": sum(1 for item in all_items if item.owner_user_id is None),
            "resolved_recently": count_resolved_recently(all_items),
        },
        items=[ExceptionListItem.model_validate(item) for item in serialized],
    )


@router.get("/export.csv")
def export_exceptions(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    severity: Annotated[str | None, Query()] = None,
    type: Annotated[str | None, Query()] = None,
    plant_id: Annotated[int | None, Query()] = None,
    material_id: Annotated[int | None, Query()] = None,
    shipment_id: Annotated[str | None, Query()] = None,
    owner_user_id: Annotated[int | None, Query()] = None,
    unassigned_only: Annotated[bool, Query()] = False,
):
    items, _ = list_exception_records(
        db,
        context,
        status=status_filter,
        severity=severity,
        type=type,
        plant_id=plant_id,
        material_id=material_id,
        shipment_id=shipment_id,
        owner_user_id=owner_user_id,
        unassigned_only=unassigned_only,
    )
    serialized = [serialize_exception(db, context, item) for item in items]
    return build_csv_response(
        filename="exceptions.csv",
        fieldnames=[
            "id",
            "type",
            "severity",
            "status",
            "title",
            "plant",
            "material",
            "shipment_id",
            "owner",
            "recommended_next_step",
            "triggered_at",
            "updated_at",
        ],
        rows=[
            {
                "id": item["id"],
                "type": item["type"],
                "severity": item["severity"],
                "status": item["status"],
                "title": item["title"],
                "plant": item["linked_plant"]["label"] if item["linked_plant"] else None,
                "material": (
                    item["linked_material"]["label"] if item["linked_material"] else None
                ),
                "shipment_id": (
                    item["linked_shipment"]["label"] if item["linked_shipment"] else None
                ),
                "owner": (
                    item["current_owner"]["full_name"] if item["current_owner"] else None
                ),
                "recommended_next_step": item["recommended_next_step"],
                "triggered_at": item["triggered_at"],
                "updated_at": item["updated_at"],
            }
            for item in serialized
        ],
    )


@router.get("/{exception_id}", response_model=ExceptionDetailResponse)
def exception_detail(
    exception_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> ExceptionDetailResponse:
    record = get_exception_detail(db, context, exception_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")
    return ExceptionDetailResponse(
        exception=ExceptionListItem.model_validate(serialize_exception(db, context, record)),
        linked_shipment_detail=linked_shipment_detail(db, record),
        linked_context_notes=detail_context_notes(db, context, record),
        comments=[
            ExceptionCommentOut.model_validate(item)
            for item in list_comments(db, context, record.id)
        ],
        status_options=(
            ["open", "in_progress"]
            if record.summary and any(
                record.summary.startswith(f"[trigger_source:{trigger}]")
                for trigger in VALID_TRIGGER_TYPES
            )
            else ["open", "in_progress", "resolved", "closed"]
        ),
    )


@router.post("/evaluate", response_model=ExceptionEvaluationResponse)
def evaluate_exception_rules(
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> ExceptionEvaluationResponse:
    created, updated, resolved, open_after = evaluate_exceptions(db, context)
    return ExceptionEvaluationResponse(
        created=created,
        updated=updated,
        resolved=resolved,
        open_after_evaluation=open_after,
    )


@router.patch("/{exception_id}/owner", response_model=ExceptionListItem)
def assign_owner(
    exception_id: int,
    payload: ExceptionAssignmentRequest,
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> ExceptionListItem:
    record = get_exception_detail(db, context, exception_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")
    try:
        updated = assign_exception_owner(db, context, record, payload.owner_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExceptionListItem.model_validate(serialize_exception(db, context, updated))


@router.patch("/{exception_id}/status", response_model=ExceptionListItem)
def change_status(
    exception_id: int,
    payload: ExceptionStatusRequest,
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> ExceptionListItem:
    record = get_exception_detail(db, context, exception_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")
    try:
        updated = update_exception_status(db, context, record, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExceptionListItem.model_validate(serialize_exception(db, context, updated))


@router.patch("/{exception_id}/action", response_model=ExceptionListItem)
def change_action_status(
    exception_id: int,
    payload: ExceptionActionRequest,
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> ExceptionListItem:
    record = get_exception_detail(db, context, exception_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")
    try:
        updated = update_exception_action_status(db, context, record, payload.action_status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExceptionListItem.model_validate(serialize_exception(db, context, updated))


@router.post("/{exception_id}/comments", response_model=ExceptionCommentOut)
def create_comment(
    exception_id: int,
    payload: ExceptionCommentRequest,
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> ExceptionCommentOut:
    record = get_exception_detail(db, context, exception_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")
    comment = payload.comment.strip()
    if not comment:
        raise HTTPException(status_code=400, detail="Comment is required")
    add_exception_comment(db, context, record, comment)
    latest = list_comments(db, context, record.id)[-1]
    return ExceptionCommentOut.model_validate(latest)
