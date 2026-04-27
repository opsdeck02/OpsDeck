from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_db,
    get_request_context,
    require_admin_access,
    require_superadmin,
)
from app.models import User
from app.modules.auth.constants import TENANT_ADMIN
from app.modules.tenants.schemas import (
    ExternalDataSourceCreateRequest,
    ExternalDataSourceOut,
    ExternalDataSourceSyncResult,
    ExternalDataSourceUpdateRequest,
    TenantCreatedResponse,
    TenantCreateRequest,
    TenantPlanSummaryOut,
    TenantPlanUpdateRequest,
    TenantSummaryOut,
)
from app.modules.tenants.sync_service import sync_data_source_now
from app.modules.tenants.service import (
    TenantAdminPayload,
    activate_tenant,
    create_tenant,
    create_data_source,
    deactivate_tenant,
    delete_data_source,
    delete_tenant,
    ensure_numbered_plants,
    get_tenant_details,
    get_tenant_plan,
    list_data_sources,
    list_all_tenants,
    update_data_source,
    update_tenant_plan,
)
from app.schemas.context import RequestContext


# Additional response models
class TenantDetailOut(BaseModel):
    id: int
    name: str
    slug: str
    plan_tier: str
    max_users: int | None
    is_active: bool
    access_weeks: int | None
    access_expires_at: str | None
    days_until_expiry: int | None
    active_user_count: int
    created_at: str
    users: list[dict]
    capabilities: dict[str, bool]


class TenantActivateDeactivateOut(BaseModel):
    id: int
    name: str
    slug: str
    is_active: bool


class TenantPlantBootstrapRequest(BaseModel):
    count: int
    plant_names: list[str] = []


class TenantPlantBootstrapResponse(BaseModel):
    created: int
    renamed: int
    total: int


router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("")
def list_tenants(
    current_user: Annotated[User, Depends(get_current_user)],
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> list[dict[str, str]]:
    if current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin does not have access to tenant operational data",
        )
    return [{"name": "Demo Steel Plant", "slug": context.tenant_slug or "default"}]


@router.post("/plants", response_model=TenantPlantBootstrapResponse)
def bootstrap_tenant_plants(
    payload: TenantPlantBootstrapRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantPlantBootstrapResponse:
    if current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin cannot configure plants through a tenant session",
        )
    if not any(
        membership.tenant_id == context.tenant_id and membership.role.name == TENANT_ADMIN
        for membership in current_user.memberships
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tenant admins can configure plant setup",
        )

    try:
        result = ensure_numbered_plants(
            db,
            context.tenant_id,
            payload.count,
            payload.plant_names,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TenantPlantBootstrapResponse(**result)


@router.get("/plan", response_model=TenantPlanSummaryOut)
def get_current_tenant_plan(
    _: Annotated[RequestContext, Depends(require_admin_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantPlanSummaryOut:
    plan = get_tenant_plan(db, context.tenant_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantPlanSummaryOut.model_validate(plan)


@router.get("/data-sources", response_model=list[ExternalDataSourceOut])
def list_current_tenant_data_sources(
    _: Annotated[RequestContext, Depends(require_admin_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ExternalDataSourceOut]:
    try:
        rows = list_data_sources(db, context.tenant_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [ExternalDataSourceOut.model_validate(row) for row in rows]


@router.post("/data-sources", response_model=ExternalDataSourceOut)
def create_current_tenant_data_source(
    payload: ExternalDataSourceCreateRequest,
    _: Annotated[RequestContext, Depends(require_admin_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> ExternalDataSourceOut:
    try:
        row = create_data_source(
            db,
            tenant_id=context.tenant_id,
            source_type=payload.source_type,
            source_url=payload.source_url.strip(),
            source_name=payload.source_name.strip(),
            dataset_type=payload.dataset_type,
            mapping_config=payload.mapping_config,
            sync_frequency_minutes=payload.sync_frequency_minutes,
            is_active=payload.is_active,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ExternalDataSourceOut.model_validate(row)


@router.put("/data-sources/{source_id}", response_model=ExternalDataSourceOut)
def update_current_tenant_data_source(
    source_id: int,
    payload: ExternalDataSourceUpdateRequest,
    _: Annotated[RequestContext, Depends(require_admin_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> ExternalDataSourceOut:
    try:
        row = update_data_source(
            db,
            tenant_id=context.tenant_id,
            source_id=source_id,
            source_type=payload.source_type,
            source_url=payload.source_url.strip(),
            source_name=payload.source_name.strip(),
            dataset_type=payload.dataset_type,
            mapping_config=payload.mapping_config,
            sync_frequency_minutes=payload.sync_frequency_minutes,
            is_active=payload.is_active,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ExternalDataSourceOut.model_validate(row)


@router.delete("/data-sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_tenant_data_source(
    source_id: int,
    _: Annotated[RequestContext, Depends(require_admin_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    try:
        delete_data_source(db, tenant_id=context.tenant_id, source_id=source_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/data-sources/{source_id}/sync", response_model=ExternalDataSourceSyncResult)
def sync_current_tenant_data_source(
    source_id: int,
    _: Annotated[RequestContext, Depends(require_admin_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ExternalDataSourceSyncResult:
    try:
        result = sync_data_source_now(
            db,
            context=context,
            current_user_id=current_user.id,
            source_id=source_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ExternalDataSourceSyncResult.model_validate(result)


@router.get("/admin/all", response_model=list[TenantSummaryOut])
def list_all_tenants_for_superadmin(
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[TenantSummaryOut]:
    return [TenantSummaryOut.model_validate(item) for item in list_all_tenants(db)]


@router.post("/admin", response_model=TenantCreatedResponse)
def create_tenant_for_superadmin(
    payload: TenantCreateRequest,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantCreatedResponse:
    try:
        created = create_tenant(
            db,
            name=payload.name.strip(),
            slug=payload.slug.strip().lower(),
            plan_tier=payload.plan_tier,
            max_users=payload.max_users,
            access_weeks=payload.access_weeks,
            admin_user=(
                TenantAdminPayload(
                    email=payload.admin_user.email.strip().lower(),
                    full_name=payload.admin_user.full_name.strip(),
                    password=payload.admin_user.password,
                )
                if payload.admin_user
                else None
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TenantCreatedResponse.model_validate(created)


@router.patch("/admin/{tenant_id}/plan", response_model=TenantPlanSummaryOut)
def update_tenant_plan_for_superadmin(
    tenant_id: int,
    payload: TenantPlanUpdateRequest,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantPlanSummaryOut:
    try:
        result = update_tenant_plan(db, tenant_id, payload.plan_tier)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TenantPlanSummaryOut.model_validate(result)


@router.get("/admin/{tenant_id}", response_model=TenantDetailOut)
def get_tenant_details_for_superadmin(
    tenant_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantDetailOut:
    details = get_tenant_details(db, tenant_id)
    if details is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    # Calculate days until expiry for the dashboard view
    expires_at = details.get("access_expires_at")
    if expires_at:
        now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now(timezone.utc)
        delta = expires_at - now
        details["days_until_expiry"] = max(0, delta.days)
    else:
        details["days_until_expiry"] = None

    # Convert datetime to string
    details["access_expires_at"] = details["access_expires_at"].isoformat() if details["access_expires_at"] else None
    details["created_at"] = details["created_at"].isoformat()
    return TenantDetailOut(**details)


@router.post("/admin/{tenant_id}/activate", response_model=TenantActivateDeactivateOut)
def activate_tenant_for_superadmin(
    tenant_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantActivateDeactivateOut:
    try:
        result = activate_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TenantActivateDeactivateOut(**result)


@router.post("/admin/{tenant_id}/users/{user_id}/toggle", response_model=dict)
def toggle_tenant_user_status(
    tenant_id: int,
    user_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Toggle a user's active status within a specific tenant (Superadmin only)"""
    try:
        from app.modules.tenants.service import toggle_tenant_user_status as toggle_svc

        new_status = toggle_svc(db, tenant_id, user_id)
        return {"user_id": user_id, "is_active": new_status}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/admin/{tenant_id}/deactivate", response_model=TenantActivateDeactivateOut)
def deactivate_tenant_for_superadmin(
    tenant_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantActivateDeactivateOut:
    try:
        result = deactivate_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TenantActivateDeactivateOut(**result)


@router.delete("/admin/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant_for_superadmin(
    tenant_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    if any(membership.tenant_id == tenant_id for membership in current_user.memberships):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Superadmin cannot delete the tenant used by the current session",
        )
    try:
        delete_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
