from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import MicrosoftConnection
from app.modules.microsoft.service import refresh_access_token
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="opsdeck.microsoft.refresh_tokens")
def refresh_expiring_tokens() -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    cutoff = datetime.now(UTC) + timedelta(minutes=30)
    with SessionLocal() as db:
        connections = list(
            db.scalars(
                select(MicrosoftConnection).where(
                    MicrosoftConnection.is_active.is_(True),
                    MicrosoftConnection.token_expires_at < cutoff,
                )
            )
        )
        for connection in connections:
            try:
                refresh_access_token(db, connection)
                results.append({"connection_id": str(connection.id), "status": "success"})
            except Exception as exc:
                logger.exception(
                    "Microsoft token refresh failed",
                    extra={"connection_id": str(connection.id)},
                )
                results.append({"connection_id": str(connection.id), "status": "error", "error": str(exc)})
    return results
