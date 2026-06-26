from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TenantScopedMixin, TimestampMixin


class TenantOperationalMilestone(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "tenant_operational_milestones"
    __table_args__ = (Index("ix_operational_milestones_tenant", "tenant_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    milestone_type: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TenantOperationalNote(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "tenant_operational_notes"
    __table_args__ = (Index("ix_operational_notes_tenant", "tenant_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    note_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attendees: Mapped[list[str] | None] = mapped_column(JSON)
    actions: Mapped[list[str] | None] = mapped_column(JSON)
    note_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TenantReportSnapshot(TenantScopedMixin, Base):
    __tablename__ = "tenant_report_snapshots"
    __table_args__ = (
        Index("ix_tenant_report_snapshots_tenant", "tenant_id"),
        Index(
            "ix_tenant_report_snapshots_period",
            "tenant_id",
            "report_type",
            "period_start",
            "period_end",
            "version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_type: Mapped[str] = mapped_column(String(30), nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    snapshot_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    pdf_bytes: Mapped[bytes | None] = mapped_column(LargeBinary)
    generated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantWeeklyReview(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "tenant_weekly_reviews"
    __table_args__ = (
        Index("ix_tenant_weekly_reviews_tenant", "tenant_id"),
        Index("ix_tenant_weekly_reviews_tenant_week", "tenant_id", "week_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    review_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    review_title: Mapped[str] = mapped_column(String(255), nullable=False)
    attendees: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    meeting_summary: Mapped[str | None] = mapped_column(Text)
    operational_observations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    customer_feedback: Mapped[str | None] = mapped_column(Text)
    agreed_actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    blockers: Mapped[str | None] = mapped_column(Text)
    next_focus: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class TenantReviewAction(Base):
    __tablename__ = "tenant_review_actions"
    __table_args__ = (Index("ix_tenant_review_actions_weekly_review", "weekly_review_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    weekly_review_id: Mapped[int] = mapped_column(
        ForeignKey("tenant_weekly_reviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(120))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="Open")
