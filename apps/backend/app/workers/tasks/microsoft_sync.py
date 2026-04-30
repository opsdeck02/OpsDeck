from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import MicrosoftConnection, MicrosoftDataSource
from app.modules.microsoft.service import sync_microsoft_data_source
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="opsdeck.microsoft.sync_all")
def sync_all_microsoft_sources() -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    now = datetime.now(UTC)
    with SessionLocal() as db:
        sources = list(
            db.scalars(
                select(MicrosoftDataSource)
                .join(
                    MicrosoftConnection,
                    MicrosoftConnection.id == MicrosoftDataSource.microsoft_connection_id,
                )
                .where(
                    MicrosoftDataSource.is_active.is_(True),
                    MicrosoftDataSource.sync_status != "syncing",
                    MicrosoftConnection.is_active.is_(True),
                )
            )
        )
        for source in sources:
            if source.last_successful_sync_at is not None:
                last_success = source.last_successful_sync_at
                if last_success.tzinfo is None:
                    last_success = last_success.replace(tzinfo=UTC)
                if now - last_success < timedelta(minutes=source.sync_frequency_minutes):
                    continue
            try:
                sync_microsoft_data_source(db, source)
                results.append({"source_id": str(source.id), "status": "success"})
            except Exception as exc:
                logger.exception("Microsoft source sync failed", extra={"source_id": str(source.id)})
                results.append({"source_id": str(source.id), "status": "error", "error": str(exc)})
    return results
