from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class NotificationSettingsPayload(BaseModel):
    critical_alerts_enabled: bool = True
    weekly_digest_enabled: bool = True
    recipients_to: list[str] = Field(default_factory=list)
    recipients_cc: list[str] = Field(default_factory=list)
    pilot_contacts: list[str] = Field(default_factory=list)
    digest_day: str = "monday"
    digest_time: str = "08:00"
    tenant_timezone: str = "Asia/Kolkata"
    cooldown_hours: int = Field(default=24, ge=1, le=168)


class NotificationSettingsRead(NotificationSettingsPayload):
    id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NotificationDeliveryLogRead(BaseModel):
    id: int
    tenant_id: int
    notification_type: str
    recipient: str
    subject: str
    sent_at: datetime
    status: str
    condition_key: str | None
    error_message: str | None

    model_config = {"from_attributes": True}


class NotificationDispatchResult(BaseModel):
    subject: str
    notification_type: str
    status: str
    recipients_to: list[str]
    recipients_cc: list[str]
    skipped_reason: str | None = None
    logs: list[NotificationDeliveryLogRead]
