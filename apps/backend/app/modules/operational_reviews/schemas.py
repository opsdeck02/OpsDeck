from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewActionCreate(BaseModel):
    description: str = Field(min_length=1)
    owner: str | None = Field(default=None, max_length=120)
    due_date: date | None = None
    status: str = "Open"


class ReviewActionUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1)
    owner: str | None = Field(default=None, max_length=120)
    due_date: date | None = None
    status: str | None = None


class ReviewActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    weekly_review_id: int
    description: str
    owner: str | None
    due_date: date | None
    status: str


class WeeklyReviewCreate(BaseModel):
    week_number: int = Field(gt=0)
    review_date: datetime
    review_title: str = Field(min_length=1, max_length=255)
    attendees: list[str] = []
    meeting_summary: str | None = None
    operational_observations: list[str] = []
    customer_feedback: str | None = None
    agreed_actions: list[ReviewActionCreate] = []
    blockers: str | None = None
    next_focus: str | None = None


class WeeklyReviewUpdate(BaseModel):
    week_number: int | None = Field(default=None, gt=0)
    review_date: datetime | None = None
    review_title: str | None = Field(default=None, min_length=1, max_length=255)
    attendees: list[str] | None = None
    meeting_summary: str | None = None
    operational_observations: list[str] | None = None
    customer_feedback: str | None = None
    agreed_actions: list[ReviewActionCreate] | None = None
    blockers: str | None = None
    next_focus: str | None = None


class WeeklyReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    week_number: int
    review_date: datetime
    review_title: str
    attendees: list[str]
    meeting_summary: str | None
    operational_observations: list[str]
    customer_feedback: str | None
    agreed_actions: list[dict]
    blockers: str | None
    next_focus: str | None
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    actions: list[ReviewActionOut] = []
