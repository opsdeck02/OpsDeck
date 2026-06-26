from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TenantBasicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    plan_tier: str
    is_active: bool
    is_demo_tenant: bool
    created_at: datetime


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    milestone_type: str = Field(default="weekly_review", max_length=60)
    status: str = Field(default="pending", max_length=20)
    occurred_at: datetime | None = None


class MilestoneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    milestone_type: str | None = Field(default=None, max_length=60)
    status: str | None = Field(default=None, max_length=20)
    occurred_at: datetime | None = None


class MilestoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    title: str
    description: str | None
    milestone_type: str
    status: str
    occurred_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NoteCreate(BaseModel):
    note_type: str = Field(default="weekly_review", max_length=60)
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    attendees: list[str] | None = None
    actions: list[str] | None = None
    note_date: datetime | None = None


class NoteUpdate(BaseModel):
    note_type: str | None = Field(default=None, max_length=60)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = Field(default=None, min_length=1)
    attendees: list[str] | None = None
    actions: list[str] | None = None
    note_date: datetime | None = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    note_type: str
    title: str
    body: str
    attendees: list[str] | None
    actions: list[str] | None
    note_date: datetime | None
    created_at: datetime
    updated_at: datetime


class ReportGenerateRequest(BaseModel):
    report_type: str = Field(default="pilot", max_length=30)
    period_start: date | None = None
    period_end: date | None = None
    title: str = Field(default="Focused Evaluation Report", min_length=1, max_length=255)


class ReportSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    report_type: str
    period_start: date | None
    period_end: date | None
    version: int
    title: str
    summary: str | None
    snapshot_payload: dict[str, Any]
    generated_by_user_id: int | None
    generated_at: datetime
    created_at: datetime


class OperationalHistorySummary(BaseModel):
    tenant: TenantBasicOut
    milestone_count: int
    note_count: int
    report_count: int
    latest_report: ReportSnapshotOut | None
    recent_milestones: list[MilestoneOut]
    recent_notes: list[NoteOut]
