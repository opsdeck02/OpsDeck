from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ExternalDataSource, Role, TenantMembership
from app.modules.auth.constants import TENANT_ADMIN
from app.modules.tenants.service import classify_data_freshness
from app.modules.tenants.sync_service import sync_loaded_data_source
from app.schemas.context import RequestContext

logger = logging.getLogger(__name__)
SCHEDULER_SCAN_INTERVAL_SECONDS = 60


async def scheduler_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            process_due_data_sources_once()
        except Exception:
            logger.exception("Automated data-source scheduler loop failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SCHEDULER_SCAN_INTERVAL_SECONDS)
        except TimeoutError:
            continue


def process_due_data_sources_once(now: datetime | None = None) -> None:
    current_time = now or datetime.now(UTC)
    with SessionLocal() as db:
        sources = list(
            db.scalars(
                select(ExternalDataSource)
                .where(ExternalDataSource.is_active.is_(True))
                .order_by(ExternalDataSource.id.asc())
            )
        )
        for source in sources:
            if not is_source_due(source, current_time):
                continue
            try:
                context = RequestContext(
                    tenant_id=source.tenant_id,
                    tenant_slug=resolve_tenant_slug(db, source.tenant_id),
                    role=TENANT_ADMIN,
                    user_id=resolve_scheduler_user_id(db, source.tenant_id) or 0,
                )
                sync_loaded_data_source(
                    db,
                    context=context,
                    current_user_id=context.user_id,
                    source=source,
                )
            except Exception:
                logger.exception(
                    "Automated data-source scheduled sync failed for source %s",
                    source.id,
                )
                db.rollback()


def is_source_due(source: ExternalDataSource, now: datetime | None = None) -> bool:
    current_time = now or datetime.now(UTC)
    freshness_status, age_minutes = classify_data_freshness(
        source.last_synced_at,
        source.sync_frequency_minutes,
        now=current_time,
    )
    if source.last_synced_at is None:
        return True
    if age_minutes is None:
        return freshness_status != "fresh"
    return age_minutes >= source.sync_frequency_minutes


def resolve_tenant_slug(db, tenant_id: int) -> str:
    from app.models import Tenant

    tenant = db.get(Tenant, tenant_id)
    return tenant.slug if tenant is not None else f"tenant-{tenant_id}"


def resolve_scheduler_user_id(db, tenant_id: int) -> int | None:
    membership = db.scalar(
        select(TenantMembership.user_id)
        .join(Role, TenantMembership.role_id == Role.id)
        .where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.is_active.is_(True),
            Role.name == TENANT_ADMIN,
        )
    )
    return membership
