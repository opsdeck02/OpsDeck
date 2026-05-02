from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import get_current_user, get_db
from app.models import TenantMembership, User
from app.modules.auth.lockout import login_attempt_limiter
from app.modules.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    verify_password,
)
from app.modules.tenants.service import ensure_tenant_access_state
from app.schemas.auth import (
    CurrentUser,
    LoginRequest,
    RefreshRequest,
    TenantMembershipOut,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def me(current_user: Annotated[User, Depends(get_current_user)]) -> CurrentUser:
    return serialize_current_user(current_user)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    limiter_key = f"{request.client.host if request.client else 'unknown'}:{payload.email.lower()}"
    if login_attempt_limiter.is_locked(limiter_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again in 15 minutes.",
        )

    user = db.execute(
        select(User)
        .options(
            joinedload(User.memberships).joinedload(TenantMembership.tenant),
            joinedload(User.memberships).joinedload(TenantMembership.role),
        )
        .where(User.email == payload.email.lower(), User.is_active.is_(True))
    ).unique().scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.password_hash):
        login_attempt_limiter.record_failure(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    login_attempt_limiter.record_success(limiter_key)
    for membership in user.memberships:
        ensure_tenant_access_state(db, membership.tenant)

    return TokenResponse(
        access_token=create_access_token(subject=str(user.id)),
        refresh_token=create_refresh_token(subject=str(user.id)),
        user=serialize_current_user(user),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    token_payload = decode_access_token(payload.refresh_token)
    if token_payload.get("typ") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    user_id = token_payload.get("sub")
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
    return TokenResponse(
        access_token=create_access_token(subject=str(user.id)),
        refresh_token=payload.refresh_token,
        user=serialize_current_user(user),
    )


def serialize_current_user(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_superadmin=user.is_superadmin,
        memberships=[
            TenantMembershipOut(
                tenant_id=membership.tenant_id,
                tenant_name=membership.tenant.name,
                tenant_slug=membership.tenant.slug,
                role=membership.role.name,
            )
            for membership in user.memberships
            if membership.is_active and membership.tenant.is_active
        ],
    )
