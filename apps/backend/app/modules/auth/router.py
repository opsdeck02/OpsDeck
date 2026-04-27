from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import get_current_user, get_db
from app.models import TenantMembership, User
from app.modules.auth.security import create_access_token, verify_password
from app.modules.tenants.service import ensure_tenant_access_state
from app.schemas.auth import CurrentUser, LoginRequest, TenantMembershipOut, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def me(current_user: Annotated[User, Depends(get_current_user)]) -> CurrentUser:
    return serialize_current_user(current_user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    user = db.execute(
        select(User)
        .options(
            joinedload(User.memberships).joinedload(TenantMembership.tenant),
            joinedload(User.memberships).joinedload(TenantMembership.role),
        )
        .where(User.email == payload.email.lower(), User.is_active.is_(True))
    ).unique().scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    for membership in user.memberships:
        ensure_tenant_access_state(db, membership.tenant)

    return TokenResponse(
        access_token=create_access_token(subject=str(user.id)),
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
