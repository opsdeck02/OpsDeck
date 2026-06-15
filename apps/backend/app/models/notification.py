from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TenantScopedMixin, TimestampMixin


class NotificationSettings(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "notification_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_notification_settings_tenant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    critical_alerts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    weekly_digest_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    recipients_to: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    recipients_cc: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    pilot_contacts: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    digest_day: Mapped[str] = mapped_column(String(16), nullable=False, default="monday")
    digest_time: Mapped[str] = mapped_column(String(8), nullable=False, default="08:00")
    tenant_timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="Asia/Kolkata")
    cooldown_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)


class NotificationDeliveryLog(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "notification_delivery_logs"
    __table_args__ = (
        Index("ix_notification_logs_tenant_sent_at", "tenant_id", "sent_at"),
        Index(
            "ix_notification_logs_tenant_alert_key",
            "tenant_id",
            "notification_type",
            "condition_key",
            "sent_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    notification_type: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    condition_key: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
