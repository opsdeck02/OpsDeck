from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TimestampMixin


class MicrosoftConnection(TimestampMixin, Base):
    __tablename__ = "microsoft_connections"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "microsoft_user_id",
            name="uq_microsoft_connections_tenant_user",
        ),
        Index("ix_microsoft_connections_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    microsoft_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    microsoft_tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    auth_error: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_token_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
