from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.session import SessionLocal
from app.models import TenantMembership, User
from app.modules.auth.constants import (
    BUYER_USER,
    LOGISTICS_USER,
    MANAGEMENT_USER,
    PLANNER_USER,
    SPONSOR_USER,
    TENANT_ADMIN,
)
from app.modules.auth.security import decode_access_token
from app.modules.tenants.service import ensure_tenant_access_state
from app.schemas.context import RequestContext

bearer_scheme = HTTPBearer(auto_error=False)
OPERATOR_ROLES = (TENANT_ADMIN, BUYER_USER, LOGISTICS_USER, PLANNER_USER)
READ_ONLY_ROLES = (*OPERATOR_ROLES, MANAGEMENT_USER, SPONSOR_USER)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        )

    user = db.execute(
        select(User)
        .options(
            joinedload(User.memberships).joinedload(TenantMembership.tenant),
            joinedload(User.memberships).joinedload(TenantMembership.role),
        )
        .where(User.id == int(user_id), User.is_active.is_(True))
    ).unique().scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


def get_request_context(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    x_tenant_slug: Annotated[str | None, Header(alias="X-Tenant-Slug")] = None,
) -> RequestContext:
    active_memberships: list[TenantMembership] = []
    for membership in current_user.memberships:
        if not membership.is_active:
            continue
        if ensure_tenant_access_state(db, membership.tenant):
            active_memberships.append(membership)
    memberships = active_memberships
    selected_membership = None

    if x_tenant_slug:
        selected_membership = next(
            (
                membership
                for membership in memberships
                if membership.tenant.slug == x_tenant_slug
            ),
            None,
        )
    elif memberships:
        selected_membership = memberships[0]

    if selected_membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active membership for requested tenant",
        )

    return RequestContext(
        tenant_id=selected_membership.tenant_id,
        tenant_slug=selected_membership.tenant.slug,
        role=selected_membership.role.name,
        user_id=current_user.id,
    )


def require_roles(*allowed_roles: str):
    def dependency(
        context: Annotated[RequestContext, Depends(get_request_context)],
    ) -> RequestContext:
        if context.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role is not allowed to access this resource",
            )
        return context

    return dependency


def require_operator_access(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> RequestContext:
    if context.role not in OPERATOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role is not allowed to manage tenant operations",
        )
    return context


def require_admin_access(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> RequestContext:
    if context.role != TENANT_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role is not allowed to access tenant admin resources",
        )
    return context


def require_superadmin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access is required for this resource",
        )
    return current_user
