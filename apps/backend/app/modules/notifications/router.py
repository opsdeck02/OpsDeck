from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_admin_access
from app.modules.notifications.schemas import (
    NotificationDispatchResult,
    NotificationSettingsPayload,
    NotificationSettingsRead,
)
from app.modules.notifications.service import (
    get_notification_settings,
    send_test_critical_alert,
    send_test_weekly_digest,
    update_notification_settings,
)
from app.schemas.context import RequestContext

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/settings", response_model=NotificationSettingsRead)
def read_notification_settings(
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> NotificationSettingsRead:
    return NotificationSettingsRead.model_validate(get_notification_settings(db, context))


@router.put("/settings", response_model=NotificationSettingsRead)
def save_notification_settings(
    payload: NotificationSettingsPayload,
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> NotificationSettingsRead:
    return update_notification_settings(db, context, payload)


@router.post("/test-digest", response_model=NotificationDispatchResult)
def send_test_digest(
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> NotificationDispatchResult:
    return send_test_weekly_digest(db, context)


@router.post("/test-critical-alert", response_model=NotificationDispatchResult)
def send_test_critical(
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> NotificationDispatchResult:
    return send_test_critical_alert(db, context)
