from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TenantScopedMixin, TimestampMixin


class ExternalDataSource(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "external_data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(40), nullable=False)
    platform_detected: Mapped[str | None] = mapped_column(String(40))
    mapping_config_json: Mapped[str | None] = mapped_column(Text)
    sync_frequency_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(40))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    new_critical_risks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolved_risks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    newly_breached_actions_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
