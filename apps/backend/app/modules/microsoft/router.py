from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_request_context, require_admin_access
from app.models import MicrosoftConnection, MicrosoftDataSource
from app.modules.ingestion.service import preview_header_mapping
from app.modules.microsoft import service
from app.modules.microsoft.schemas import (
    MicrosoftAuthUrlOut,
    MicrosoftConnectionOut,
    MicrosoftDataSourceCreate,
    MicrosoftDataSourceOut,
    MicrosoftDataSourceUpdate,
    MicrosoftDriveOut,
    MicrosoftFileOut,
    MicrosoftSharePointSiteOut,
    MicrosoftSheetNamesOut,
    MicrosoftSyncResult,
)
from app.schemas.context import RequestContext

router = APIRouter(prefix="/microsoft", tags=["microsoft"])


@router.get("/auth-url", response_model=MicrosoftAuthUrlOut)
def auth_url(
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> MicrosoftAuthUrlOut:
    url, state = service.get_authorization_url(db, context.tenant_id, context.user_id or 0)
    return MicrosoftAuthUrlOut(auth_url=url, state=state)


@router.get("/callback", include_in_schema=False)
def callback(
    db: Annotated[Session, Depends(get_db)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        return RedirectResponse(f"/dashboard/onboarding?microsoft=error&message={error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing Microsoft OAuth code or state")
    try:
        service.handle_callback(db, code, state)
    except HTTPException:
        raise
    except Exception as exc:
        return RedirectResponse(f"/dashboard/onboarding?microsoft=error&message={str(exc)}")
    return RedirectResponse("/dashboard/onboarding?microsoft=connected")


@router.get("/connections", response_model=list[MicrosoftConnectionOut])
def list_connections(
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> list[MicrosoftConnection]:
    return list(
        db.scalars(
            select(MicrosoftConnection)
            .where(MicrosoftConnection.tenant_id == context.tenant_id)
            .order_by(MicrosoftConnection.connected_at.desc())
        )
    )


@router.delete("/connections/{connection_id}", response_model=MicrosoftConnectionOut)
def delete_connection(
    connection_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[RequestContext, Depends(require_admin_access)],
) -> MicrosoftConnection:
    connection = _get_connection(db, context.tenant_id, connection_id)
    connection.is_active = False
    for source in db.scalars(
        select(MicrosoftDataSource).where(
            MicrosoftDataSource.tenant_id == context.tenant_id,
            MicrosoftDataSource.microsoft_connection_id == connection_id,
        )
    ):
        source.is_active = False
    db.commit()
    db.refresh(connection)
    return connection


@router.get("/connections/{connection_id}/files/sheet-names", response_model=MicrosoftSheetNamesOut)
def sheet_names(
    connection_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    drive_id: str = Query(...),
    item_id: str = Query(...),
    site_id: str | None = Query(default=None),
) -> MicrosoftSheetNamesOut:
    connection = _get_connection(db, context.tenant_id, connection_id)
    return MicrosoftSheetNamesOut(
        sheet_names=service.get_sheet_names(db, connection, drive_id, item_id, site_id)
    )


@router.get("/connections/{connection_id}/files/mapping-preview")
def microsoft_mapping_preview(
    connection_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    drive_id: str = Query(...),
    item_id: str = Query(...),
    file_type: str = Query(...),
    site_id: str | None = Query(default=None),
    sheet_name: str | None = Query(default=None),
):
    connection = _get_connection(db, context.tenant_id, connection_id)
    metadata = service.get_file_metadata(db, connection, drive_id, item_id, site_id)
    filename = metadata.get("name") or "microsoft-source.xlsx"
    content = service.download_file(db, connection, drive_id, item_id, site_id)
    if sheet_name and filename.lower().endswith(".xlsx"):
        content = service.activate_sheet(content, sheet_name)
    return preview_header_mapping(
        file_type=file_type.lower().strip(),
        filename=filename,
        content=content,
    )


@router.get("/connections/{connection_id}/files", response_model=list[MicrosoftFileOut])
def files(
    connection_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    search: str | None = Query(default=None),
) -> list[dict]:
    connection = _get_connection(db, context.tenant_id, connection_id)
    return service.list_drive_files(db, connection, search_query=search)


@router.get(
    "/connections/{connection_id}/sharepoint-sites",
    response_model=list[MicrosoftSharePointSiteOut],
)
def sharepoint_sites(
    connection_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> list[dict]:
    connection = _get_connection(db, context.tenant_id, connection_id)
    return service.list_sharepoint_sites(db, connection)


@router.get(
    "/connections/{connection_id}/sharepoint-sites/{site_id}/drives",
    response_model=list[MicrosoftDriveOut],
)
def sharepoint_drives(
    connection_id: uuid.UUID,
    site_id: str,
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> list[dict]:
    connection = _get_connection(db, context.tenant_id, connection_id)
    return service.list_site_drives(db, connection, site_id)


@router.get("/connections/{connection_id}/drives/{drive_id}/files", response_model=list[MicrosoftFileOut])
def drive_files(
    connection_id: uuid.UUID,
    drive_id: str,
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    site_id: str | None = Query(default=None),
) -> list[dict]:
    connection = _get_connection(db, context.tenant_id, connection_id)
    if site_id:
        return service.list_sharepoint_files(db, connection, site_id, drive_id)
    return service.list_drive_files(db, connection, drive_id=drive_id)


@router.post("/data-sources", response_model=dict)
def create_data_source(
    payload: MicrosoftDataSourceCreate,
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[RequestContext, Depends(require_admin_access)],
) -> dict:
    connection = _get_connection(db, context.tenant_id, payload.connection_id)
    source = MicrosoftDataSource(
        tenant_id=context.tenant_id,
        microsoft_connection_id=connection.id,
        drive_id=payload.drive_id,
        item_id=payload.item_id,
        site_id=payload.site_id,
        file_type=payload.file_type,
        sheet_name=payload.sheet_name,
        column_mapping=payload.column_mapping,
        sync_frequency_minutes=payload.sync_frequency_minutes,
        display_name=payload.display_name,
        sync_status="idle",
        is_active=True,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    sync_result = service.sync_microsoft_data_source(db, source)
    return {"source": MicrosoftDataSourceOut.model_validate(source).model_dump(mode="json"), "sync_result": sync_result}


@router.get("/data-sources", response_model=list[MicrosoftDataSourceOut])
def list_data_sources(
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> list[MicrosoftDataSource]:
    return list(
        db.scalars(
            select(MicrosoftDataSource)
            .where(MicrosoftDataSource.tenant_id == context.tenant_id)
            .order_by(MicrosoftDataSource.created_at.desc())
        )
    )


@router.patch("/data-sources/{source_id}", response_model=MicrosoftDataSourceOut)
def update_data_source(
    source_id: uuid.UUID,
    payload: MicrosoftDataSourceUpdate,
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[RequestContext, Depends(require_admin_access)],
) -> MicrosoftDataSource:
    source = _get_source(db, context.tenant_id, source_id)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(source, key, value)
    db.commit()
    db.refresh(source)
    return source


@router.delete("/data-sources/{source_id}", response_model=MicrosoftDataSourceOut)
def delete_data_source(
    source_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[RequestContext, Depends(require_admin_access)],
) -> MicrosoftDataSource:
    source = _get_source(db, context.tenant_id, source_id)
    source.is_active = False
    db.commit()
    db.refresh(source)
    return source


@router.post("/data-sources/{source_id}/sync", response_model=MicrosoftSyncResult)
def sync_data_source(
    source_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    context: Annotated[RequestContext, Depends(require_admin_access)],
) -> dict:
    source = _get_source(db, context.tenant_id, source_id)
    return service.sync_microsoft_data_source(db, source)


def _get_connection(db: Session, tenant_id: int, connection_id: uuid.UUID) -> MicrosoftConnection:
    connection = db.get(MicrosoftConnection, connection_id)
    if connection is None or connection.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Microsoft connection not found")
    return connection


def _get_source(db: Session, tenant_id: int, source_id: uuid.UUID) -> MicrosoftDataSource:
    source = db.get(MicrosoftDataSource, source_id)
    if source is None or source.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Microsoft data source not found")
    return source
