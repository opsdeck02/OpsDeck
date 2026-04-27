from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_db,
    get_request_context,
    require_admin_access,
    require_operator_access,
    require_superadmin,
)
from app.models import User
from app.modules.users.schemas import TenantUserCreateRequest, TenantUserOut
from app.modules.users.service import (
    create_tenant_user,
    get_tenant_user_profile,
    list_tenant_users,
    resolve_target_tenant_id,
)
from app.schemas.context import RequestContext

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[TenantUserOut])
def list_users(
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> list[TenantUserOut]:
    return [TenantUserOut.model_validate(item) for item in list_tenant_users(db, context.tenant_id)]


@router.post("", response_model=TenantUserOut)
def create_user(
    payload: TenantUserCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantUserOut:
    if not current_user.is_superadmin:
        require_admin_access(context)
    try:
        created = create_tenant_user(
            db,
            tenant_id=resolve_target_tenant_id(context, payload.tenant_id),
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
            role_name=payload.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TenantUserOut.model_validate(created)


@router.get("/{user_id}", response_model=TenantUserOut)
def get_user_profile(
    user_id: int,
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantUserOut:
    profile = get_tenant_user_profile(db, context.tenant_id, user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return TenantUserOut.model_validate(profile)


@router.get("/admin/tenant/{tenant_id}", response_model=list[TenantUserOut])
def list_users_for_superadmin(
    tenant_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[TenantUserOut]:
    return [TenantUserOut.model_validate(item) for item in list_tenant_users(db, tenant_id)]


@router.get("/admin/tenant/{tenant_id}/{user_id}", response_model=TenantUserOut)
def get_user_profile_for_superadmin(
    tenant_id: int,
    user_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> TenantUserOut:
    profile = get_tenant_user_profile(db, tenant_id, user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return TenantUserOut.model_validate(profile)
