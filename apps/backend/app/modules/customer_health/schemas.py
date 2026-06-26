from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CustomerHealthSummary(BaseModel):
    tenant_id: int
    tenant_name: str
    tenant_slug: str
    pilot_progress_percent: int
    latest_review_date: datetime | None
    weekly_reviews_count: int
    open_actions_count: int
    completed_actions_count: int
    overdue_actions_count: int
    milestones_complete_count: int
    milestones_total_count: int
    reports_generated_count: int
    latest_report_generated_at: datetime | None
    has_pilot_report: bool
    has_weekly_reviews: bool
    has_open_blockers: bool
    readiness_status: str
    recommendation: str
    readiness_reasons: list[str]
    blockers: list[str]
    next_best_actions: list[str]
