from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TimestampMixin


class MicrosoftDataSource(TimestampMixin, Base):
    __tablename__ = "microsoft_data_sources"
    __table_args__ = (
        Index("ix_microsoft_data_sources_tenant_active", "tenant_id", "is_active"),
        Index("ix_microsoft_data_sources_due", "is_active", "sync_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    microsoft_connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("microsoft_connections.id", ondelete="CASCADE"),
    )
    drive_id: Mapped[str] = mapped_column(String(255), nullable=False)
    item_id: Mapped[str] = mapped_column(String(255), nullable=False)
    site_id: Mapped[str | None] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(40), nullable=False)
    sheet_name: Mapped[str | None] = mapped_column(String(255))
    column_mapping: Mapped[dict | None] = mapped_column(JSON)
    sync_frequency_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_error: Mapped[str | None] = mapped_column(Text)
    sync_status: Mapped[str] = mapped_column(String(40), nullable=False, default="idle")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
