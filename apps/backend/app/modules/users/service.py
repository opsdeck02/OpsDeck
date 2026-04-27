from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Role, Tenant, TenantMembership, User
from app.modules.auth.security import hash_password
from app.schemas.context import RequestContext

ALLOWED_TENANT_USER_ROLES = {
    "tenant_admin",
    "buyer_user",
    "logistics_user",
    "planner_user",
    "management_user",
    "sponsor_user",
}


def list_tenant_users(db: Session, tenant_id: int) -> list[dict]:
    memberships = list(
        db.scalars(
            select(TenantMembership)
            .where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.is_active.is_(True),
            )
            .order_by(TenantMembership.user_id.asc())
        )
    )
    rows: list[dict] = []
    for membership in memberships:
        user = db.get(User, membership.user_id)
        tenant = db.get(Tenant, membership.tenant_id)
        if user is None or tenant is None:
            continue
        rows.append(
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": membership.role.name,
                "is_active": user.is_active,
                "is_superadmin": user.is_superadmin,
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "tenant_slug": tenant.slug,
                "created_at": user.created_at,
            }
        )
    return rows


def get_tenant_user_profile(db: Session, tenant_id: int, user_id: int) -> dict | None:
    membership = db.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
        )
    )
    if membership is None:
        return None
    user = db.get(User, user_id)
    tenant = db.get(Tenant, tenant_id)
    if user is None or tenant is None:
        return None
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": membership.role.name,
        "is_active": user.is_active,
        "is_superadmin": user.is_superadmin,
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "tenant_slug": tenant.slug,
        "created_at": user.created_at,
    }


def create_tenant_user(
    db: Session,
    *,
    tenant_id: int,
    email: str,
    full_name: str,
    password: str,
    role_name: str,
) -> dict:
    if role_name not in ALLOWED_TENANT_USER_ROLES:
        raise ValueError("Unsupported tenant user role")

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found")

    active_memberships = int(
        db.scalar(
            select(func.count(TenantMembership.id)).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.is_active.is_(True),
            )
        )
        or 0
    )
    if tenant.max_users is not None and active_memberships >= tenant.max_users:
        raise ValueError("Tenant has reached its maximum allowed users")

    role = db.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise ValueError("Selected role is not available")

    normalized_email = email.lower().strip()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        user = User(
            email=normalized_email,
            full_name=full_name.strip(),
            password_hash=hash_password(password),
            is_active=True,
        )
        db.add(user)
        db.flush()

    existing_membership = db.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user.id,
        )
    )
    if existing_membership is not None:
        raise ValueError("User already belongs to this tenant")

    db.add(
        TenantMembership(
            tenant_id=tenant_id,
            user_id=user.id,
            role_id=role.id,
            is_active=True,
        )
    )
    db.commit()
    return get_tenant_user_profile(db, tenant_id, user.id) or {}


def resolve_target_tenant_id(
    context: RequestContext,
    target_tenant_id: int | None,
) -> int:
    return target_tenant_id or context.tenant_id
