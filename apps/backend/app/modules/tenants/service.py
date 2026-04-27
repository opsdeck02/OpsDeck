from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import ExternalDataSource, Plant, Role, Tenant, TenantMembership, User
from app.modules.auth.constants import TENANT_ADMIN
from app.modules.auth.security import hash_password
from app.modules.tenants.features import build_capabilities, normalize_plan_tier

DEFAULT_PILOT_ACCESS_WEEKS = 10


@dataclass
class TenantAdminPayload:
    email: str
    full_name: str
    password: str


def list_all_tenants(db: Session) -> list[dict]:
    tenants = list(db.scalars(select(Tenant).order_by(Tenant.name.asc())))
    rows: list[dict] = []
    for tenant in tenants:
        ensure_tenant_access_state(db, tenant)
        user_count = db.scalar(
            select(func.count(TenantMembership.id)).where(
                TenantMembership.tenant_id == tenant.id,
                TenantMembership.is_active.is_(True),
            )
        )
        rows.append(
            {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "plan_tier": tenant.plan_tier,
                "max_users": tenant.max_users,
                "is_active": tenant.is_active,
                "access_weeks": tenant.access_weeks,
                "access_expires_at": tenant.access_expires_at,
                "active_user_count": int(user_count or 0),
                "created_at": tenant.created_at,
            }
        )
    return rows


def create_tenant(
    db: Session,
    *,
    name: str,
    slug: str,
    max_users: int | None,
    plan_tier: str = "pilot",
    access_weeks: int | None = None,
    admin_user: TenantAdminPayload | None,
) -> dict:
    existing = db.scalar(select(Tenant).where(Tenant.slug == slug))
    if existing is not None:
        raise ValueError("A tenant with this slug already exists")

    normalized_plan_tier = normalize_plan_tier(plan_tier)
    if normalized_plan_tier == "pilot" and access_weeks is None:
        access_weeks = DEFAULT_PILOT_ACCESS_WEEKS

    # Calculate access_expires_at based on access_weeks
    access_expires_at = None
    if access_weeks is not None and access_weeks > 0:
        access_expires_at = datetime.now(timezone.utc) + timedelta(weeks=access_weeks)

    tenant = Tenant(
        name=name,
        slug=slug,
        plan_tier=normalized_plan_tier,
        max_users=max_users,
        access_weeks=access_weeks,
        access_expires_at=access_expires_at,
    )
    db.add(tenant)
    db.flush()

    created_admin = None
    if admin_user is not None:
        role = db.scalar(select(Role).where(Role.name == TENANT_ADMIN))
        if role is None:
            raise ValueError("Tenant admin role is not available")
        existing_user = db.scalar(select(User).where(User.email == admin_user.email.lower()))
        if existing_user is not None:
            raise ValueError("A user with this admin email already exists")

        user = User(
            email=admin_user.email.lower(),
            full_name=admin_user.full_name,
            password_hash=hash_password(admin_user.password),
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(
            TenantMembership(
                tenant_id=tenant.id,
                user_id=user.id,
                role_id=role.id,
                is_active=True,
            )
        )
        created_admin = {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": TENANT_ADMIN,
        }

    db.commit()
    db.refresh(tenant)
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "plan_tier": tenant.plan_tier,
        "max_users": tenant.max_users,
        "is_active": tenant.is_active,
        "access_weeks": tenant.access_weeks,
        "access_expires_at": tenant.access_expires_at,
        "created_at": tenant.created_at,
        "admin_user": created_admin,
    }


def activate_tenant(db: Session, tenant_id: int) -> dict:
    """Activate a tenant (temporary or permanent)"""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found")
    tenant.is_active = True
    if tenant.access_weeks is not None and tenant.access_weeks > 0:
        tenant.access_expires_at = datetime.now(timezone.utc) + timedelta(weeks=tenant.access_weeks)
    db.commit()
    db.refresh(tenant)
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "is_active": tenant.is_active,
    }


def deactivate_tenant(db: Session, tenant_id: int) -> dict:
    """Temporary deactivate a tenant"""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found")
    tenant.is_active = False
    db.commit()
    db.refresh(tenant)
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "is_active": tenant.is_active,
    }


def get_tenant_details(db: Session, tenant_id: int) -> dict | None:
    """Get detailed tenant information including user count and payment info"""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        return None
    ensure_tenant_access_state(db, tenant)
    
    user_count = db.scalar(
        select(func.count(TenantMembership.id)).where(
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.is_active.is_(True),
        )
    )
    
    # Get all users for this tenant
    users = list(
        db.scalars(
            select(User)
            .join(TenantMembership)
            .where(TenantMembership.tenant_id == tenant_id)
        )
    )

    days_until_expiry = None
    if tenant.access_expires_at:
        now = datetime.now(tenant.access_expires_at.tzinfo or timezone.utc)
        delta = tenant.access_expires_at - now
        days_until_expiry = max(0, delta.days)

    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "plan_tier": tenant.plan_tier,
        "max_users": tenant.max_users,
        "is_active": tenant.is_active,
        "access_weeks": tenant.access_weeks,
        "access_expires_at": tenant.access_expires_at,
        "days_until_expiry": days_until_expiry,
        "active_user_count": int(user_count or 0),
        "created_at": tenant.created_at,
        "capabilities": build_capabilities(tenant.plan_tier),
        "users": [
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "is_active": user.is_active,
            }
            for user in users
        ],
    }


def toggle_tenant_user_status(db: Session, tenant_id: int, user_id: int) -> bool:
    """Superadmin tool to enable/disable specific user access within a tenant"""
    membership = db.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id
        )
    )
    if not membership:
        raise ValueError("User membership not found for this tenant")
    
    membership.is_active = not membership.is_active
    db.commit()
    return membership.is_active


def ensure_numbered_plants(
    db: Session,
    tenant_id: int,
    count: int,
    plant_names: list[str] | None = None,
) -> dict:
    if count < 1:
        raise ValueError("Plant count must be at least 1")

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found")

    requested_names = [name.strip() for name in (plant_names or []) if name.strip()]
    existing_plants = list(db.scalars(select(Plant).where(Plant.tenant_id == tenant_id)))
    plants_by_code = {str(plant.code).upper(): plant for plant in existing_plants}
    created = 0
    renamed = 0

    for index in range(1, count + 1):
        code = f"P{index}"
        requested_name = requested_names[index - 1] if index - 1 < len(requested_names) else ""
        plant = plants_by_code.get(code)
        if plant is None:
            db.add(
                Plant(
                    tenant_id=tenant_id,
                    code=code,
                    name=requested_name or f"Plant {index}",
                    location=None,
                )
            )
            created += 1
            continue
        if requested_name and plant.name != requested_name:
            plant.name = requested_name
            renamed += 1

    db.commit()
    total = int(
        db.scalar(select(func.count(Plant.id)).where(Plant.tenant_id == tenant_id))
        or 0
    )
    return {"created": created, "renamed": renamed, "total": total}


def delete_tenant(db: Session, tenant_id: int) -> None:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found")
    db.execute(delete(TenantMembership).where(TenantMembership.tenant_id == tenant_id))
    db.execute(delete(Tenant).where(Tenant.id == tenant_id))
    db.commit()


def get_tenant_plan(db: Session, tenant_id: int) -> dict | None:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        return None
    ensure_tenant_access_state(db, tenant)
    return {
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "tenant_slug": tenant.slug,
        "plan_tier": tenant.plan_tier,
        "capabilities": build_capabilities(tenant.plan_tier),
    }


def update_tenant_plan(db: Session, tenant_id: int, plan_tier: str) -> dict:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found")
    normalized_plan_tier = normalize_plan_tier(plan_tier)
    tenant.plan_tier = normalized_plan_tier
    if normalized_plan_tier == "pilot" and tenant.access_weeks is None:
        tenant.access_weeks = DEFAULT_PILOT_ACCESS_WEEKS
        tenant.access_expires_at = datetime.now(timezone.utc) + timedelta(weeks=tenant.access_weeks)
    db.commit()
    db.refresh(tenant)
    return {
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "tenant_slug": tenant.slug,
        "plan_tier": tenant.plan_tier,
        "capabilities": build_capabilities(tenant.plan_tier),
    }


def ensure_automated_data_sources_enabled(db: Session, tenant_id: int) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found")
    if not build_capabilities(tenant.plan_tier)["automated_data_sources"]:
        raise PermissionError(
            "Automated data sources require a paid or enterprise tenant plan."
        )
    return tenant


def serialize_data_source(source: ExternalDataSource) -> dict:
    mapping_config = {}
    if source.mapping_config_json:
        try:
            mapping_config = json.loads(source.mapping_config_json)
        except json.JSONDecodeError:
            mapping_config = {}
    freshness_status, freshness_age_minutes = classify_data_freshness(
        source.last_synced_at,
        source.sync_frequency_minutes,
    )
    return {
        "id": source.id,
        "tenant_id": source.tenant_id,
        "source_type": source.source_type,
        "source_url": source.source_url,
        "source_name": source.source_name,
        "dataset_type": source.dataset_type,
        "platform_detected": source.platform_detected,
        "mapping_config": mapping_config,
        "sync_frequency_minutes": source.sync_frequency_minutes,
        "is_active": source.is_active,
        "last_sync_status": source.last_sync_status,
        "last_synced_at": source.last_synced_at,
        "last_error_message": source.last_error_message,
        "data_freshness_status": freshness_status,
        "data_freshness_age_minutes": freshness_age_minutes,
        "last_sync_summary": {
            "last_synced_at": source.last_synced_at,
            "last_sync_status": source.last_sync_status,
            "new_critical_risks_count": source.new_critical_risks_count,
            "resolved_risks_count": source.resolved_risks_count,
            "newly_breached_actions_count": source.newly_breached_actions_count,
        },
        "created_at": source.created_at,
        "updated_at": source.updated_at,
    }


def classify_data_freshness(
    last_synced_at: datetime | None,
    sync_frequency_minutes: int,
    now: datetime | None = None,
) -> tuple[str, int | None]:
    if last_synced_at is None:
        return "stale", None
    current_time = now or datetime.now(UTC)
    synced_at = last_synced_at.astimezone(UTC) if last_synced_at.tzinfo else last_synced_at.replace(tzinfo=UTC)
    age_minutes = max(0, int((current_time - synced_at).total_seconds() // 60))
    if age_minutes <= sync_frequency_minutes:
        return "fresh", age_minutes
    if age_minutes <= int(sync_frequency_minutes * 1.5):
        return "aging", age_minutes
    return "stale", age_minutes


def ensure_tenant_access_state(db: Session, tenant: Tenant) -> bool:
    expires_at = tenant.access_expires_at
    if expires_at is None:
        return tenant.is_active

    normalized_expires_at = (
        expires_at if expires_at.tzinfo is not None else expires_at.replace(tzinfo=timezone.utc)
    )
    now = datetime.now(timezone.utc)
    if normalized_expires_at < now and tenant.is_active:
        tenant.is_active = False
        db.commit()
        db.refresh(tenant)
    return tenant.is_active


def list_data_sources(db: Session, tenant_id: int) -> list[dict]:
    ensure_automated_data_sources_enabled(db, tenant_id)
    rows = list(
        db.scalars(
            select(ExternalDataSource)
            .where(ExternalDataSource.tenant_id == tenant_id)
            .order_by(ExternalDataSource.created_at.desc())
        )
    )
    return [serialize_data_source(row) for row in rows]


def create_data_source(
    db: Session,
    *,
    tenant_id: int,
    source_type: str,
    source_url: str,
    source_name: str,
    dataset_type: str,
    mapping_config: dict | None,
    sync_frequency_minutes: int,
    is_active: bool,
) -> dict:
    ensure_automated_data_sources_enabled(db, tenant_id)
    row = ExternalDataSource(
        tenant_id=tenant_id,
        source_type=source_type,
        source_url=source_url,
        source_name=source_name,
        dataset_type=dataset_type,
        mapping_config_json=json.dumps(mapping_config or {}, sort_keys=True),
        sync_frequency_minutes=sync_frequency_minutes,
        is_active=is_active,
        last_sync_status="not_started",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_data_source(row)


def update_data_source(
    db: Session,
    *,
    tenant_id: int,
    source_id: int,
    source_type: str,
    source_url: str,
    source_name: str,
    dataset_type: str,
    mapping_config: dict | None,
    sync_frequency_minutes: int,
    is_active: bool,
) -> dict:
    ensure_automated_data_sources_enabled(db, tenant_id)
    row = db.scalar(
        select(ExternalDataSource).where(
            ExternalDataSource.id == source_id,
            ExternalDataSource.tenant_id == tenant_id,
        )
    )
    if row is None:
        raise ValueError("Saved data source not found")
    row.source_type = source_type
    row.source_url = source_url
    row.source_name = source_name
    row.dataset_type = dataset_type
    row.mapping_config_json = json.dumps(mapping_config or {}, sort_keys=True)
    row.sync_frequency_minutes = sync_frequency_minutes
    row.is_active = is_active
    db.commit()
    db.refresh(row)
    return serialize_data_source(row)


def delete_data_source(db: Session, *, tenant_id: int, source_id: int) -> None:
    ensure_automated_data_sources_enabled(db, tenant_id)
    row = db.scalar(
        select(ExternalDataSource).where(
            ExternalDataSource.id == source_id,
            ExternalDataSource.tenant_id == tenant_id,
        )
    )
    if row is None:
        raise ValueError("Saved data source not found")
    db.delete(row)
    db.commit()
