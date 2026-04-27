from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TenantScopedMixin, TimestampMixin


class UploadedFile(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "uploaded_files"
    __table_args__ = (
        Index("ix_uploaded_files_tenant_status", "tenant_id", "status"),
        Index("ix_uploaded_files_tenant_uploaded_by", "tenant_id", "uploaded_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120))
    file_size_bytes: Mapped[int] = mapped_column(nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded")


class IngestionJob(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        Index("ix_ingestion_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_ingestion_jobs_tenant_source", "tenant_id", "source_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    uploaded_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("uploaded_files.id", ondelete="SET NULL")
    )
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(String)
    records_total: Mapped[int] = mapped_column(nullable=False, default=0)
    records_succeeded: Mapped[int] = mapped_column(nullable=False, default=0)
    records_failed: Mapped[int] = mapped_column(nullable=False, default=0)
