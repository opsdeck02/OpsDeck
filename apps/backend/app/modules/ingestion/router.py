import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_db,
    get_request_context,
    require_operator_access,
)
from app.models import IngestionJob, User
from app.modules.ingestion.schemas import IngestionJobOut, MappingPreviewOut, UploadResult
from app.modules.ingestion.service import (
    SUPPORTED_FILE_TYPES,
    delete_uploaded_data,
    preview_header_mapping,
    process_upload_content,
    process_upload,
)
from app.modules.ingestion.templates import TEMPLATES
from app.modules.tenants.sync_service import fetch_remote_file_for_values
from app.schemas.context import RequestContext

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.get("/sources")
def list_ingestion_sources() -> list[dict[str, str]]:
    return [
        {"name": "email", "status": "planned"},
        {"name": "ais", "status": "planned"},
        {"name": "portal-upload", "status": "mvp-ready"},
    ]


@router.post("/uploads", response_model=UploadResult)
def upload_onboarding_file(
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    mapping_overrides: Annotated[str | None, Form()] = None,
) -> UploadResult:
    parsed_overrides = parse_mapping_overrides(mapping_overrides)
    return process_upload(
        db=db,
        context=context,
        current_user_id=current_user.id,
        file_type=file_type,
        upload=file,
        mapping_overrides=parsed_overrides,
    )


@router.post("/url-upload", response_model=UploadResult)
def upload_onboarding_url(
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file_type: Annotated[str, Form()],
    source_type: Annotated[str, Form()],
    source_url: Annotated[str, Form()],
    mapping_overrides: Annotated[str | None, Form()] = None,
) -> UploadResult:
    parsed_overrides = parse_mapping_overrides(mapping_overrides)
    try:
        remote_file = fetch_remote_file_for_values(
            source_type=source_type,
            source_url=source_url,
            dataset_type=file_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    result = process_upload_content(
        db=db,
        context=context,
        current_user_id=current_user.id,
        file_type=file_type,
        filename=remote_file.filename,
        content=remote_file.content,
        content_type=remote_file.content_type,
        mapping_overrides=parsed_overrides,
        source_of_truth=source_type,
    )
    return result.model_copy(
        update={
            "platform_detected": remote_file.platform_detected,
            "transformed_url": remote_file.transformed_url,
        }
    )


@router.get("/jobs", response_model=list[IngestionJobOut])
def list_ingestion_jobs(
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> list[IngestionJobOut]:
    jobs = db.scalars(
        select(IngestionJob)
        .where(IngestionJob.tenant_id == context.tenant_id)
        .order_by(IngestionJob.created_at.desc())
        .limit(25)
    )
    return [
        IngestionJobOut(
            id=job.id,
            upload_id=job.uploaded_file_id,
            file_type=job.source_type,
            status=job.status,
            rows_received=job.records_total,
            rows_accepted=job.records_succeeded,
            rows_rejected=job.records_failed,
            error_message=job.error_message,
        )
        for job in jobs
    ]


@router.delete("/uploads")
def clear_uploaded_data(
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, int]:
    return delete_uploaded_data(db, context.tenant_id)


@router.post("/mapping-preview", response_model=MappingPreviewOut)
def preview_ingestion_mapping(
    _: Annotated[RequestContext, Depends(require_operator_access)],
    file_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> MappingPreviewOut:
    content = file.file.read()
    return preview_header_mapping(
        file_type=file_type.lower().strip(),
        filename=file.filename or "upload",
        content=content,
    )


@router.post("/url-mapping-preview", response_model=MappingPreviewOut)
def preview_url_ingestion_mapping(
    _: Annotated[RequestContext, Depends(require_operator_access)],
    file_type: Annotated[str, Form()],
    source_type: Annotated[str, Form()],
    source_url: Annotated[str, Form()],
) -> MappingPreviewOut:
    try:
        remote_file = fetch_remote_file_for_values(
            source_type=source_type,
            source_url=source_url,
            dataset_type=file_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    preview = preview_header_mapping(
        file_type=file_type.lower().strip(),
        filename=remote_file.filename,
        content=remote_file.content,
    )
    return preview.model_copy(
        update={
            "platform_detected": remote_file.platform_detected,
            "transformed_url": remote_file.transformed_url,
        }
    )


def parse_mapping_overrides(mapping_overrides: str | None) -> dict[str, str] | None:
    if not mapping_overrides:
        return None
    try:
        parsed = json.loads(mapping_overrides)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid mapping overrides payload",
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid mapping overrides payload",
        )
    return {str(key): str(value) for key, value in parsed.items() if value}


@router.get("/templates/{file_type}")
def download_template(
    file_type: str,
    _: Annotated[RequestContext, Depends(require_operator_access)],
) -> Response:
    normalized = file_type.lower().strip()
    if normalized not in SUPPORTED_FILE_TYPES:
        return Response("Unsupported file type", status_code=404)

    return Response(
        content=TEMPLATES[normalized],
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{normalized}_upload_template.csv"',
        },
    )
