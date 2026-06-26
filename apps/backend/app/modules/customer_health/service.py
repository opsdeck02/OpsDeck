from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Tenant,
    TenantOperationalMilestone,
    TenantReportSnapshot,
    TenantReviewAction,
    TenantWeeklyReview,
)
from app.modules.customer_health.schemas import CustomerHealthSummary

MAJOR_MILESTONE_TYPES = {
    "kickoff",
    "data_collection",
    "configuration",
    "historical_review",
    "final_findings",
    "monthly_review",
    "weekly_review",
}


def list_customer_health(db: Session) -> list[CustomerHealthSummary]:
    tenants = list(db.scalars(select(Tenant).order_by(Tenant.created_at.desc(), Tenant.id.asc())))
    return [customer_health_for_tenant(db, tenant.id) for tenant in tenants]


def customer_health_for_tenant(db: Session, tenant_id: int) -> CustomerHealthSummary:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found")

    milestones = list(
        db.scalars(
            select(TenantOperationalMilestone).where(
                TenantOperationalMilestone.tenant_id == tenant_id
            )
        )
    )
    reviews = list(
        db.scalars(
            select(TenantWeeklyReview).where(TenantWeeklyReview.tenant_id == tenant_id)
        )
    )
    review_ids = [review.id for review in reviews]
    actions = (
        list(
            db.scalars(
                select(TenantReviewAction).where(
                    TenantReviewAction.weekly_review_id.in_(review_ids)
                )
            )
        )
        if review_ids
        else []
    )
    reports = list(
        db.scalars(
            select(TenantReportSnapshot).where(TenantReportSnapshot.tenant_id == tenant_id)
        )
    )

    now_date = datetime.now(UTC).date()
    completed_milestones = [
        item for item in milestones if item.status.lower() == "complete"
    ]
    major_completed = {
        item.milestone_type
        for item in completed_milestones
        if item.milestone_type in MAJOR_MILESTONE_TYPES
    }
    open_actions = [item for item in actions if item.status != "Completed"]
    completed_actions = [item for item in actions if item.status == "Completed"]
    overdue_actions = [
        item
        for item in open_actions
        if item.due_date is not None and normalize_date(item.due_date) < now_date
    ]
    blocker_reviews = [item for item in reviews if item.blockers and item.blockers.strip()]
    pilot_reports = [item for item in reports if item.report_type == "pilot"]
    latest_report = max(reports, key=lambda item: item.generated_at, default=None)
    latest_review_date = max((item.review_date for item in reviews), default=None)

    has_reviews = bool(reviews)
    has_pilot_report = bool(pilot_reports)
    has_blockers = bool(blocker_reviews)
    milestones_total = len(milestones)
    milestones_complete = len(completed_milestones)
    progress = pilot_progress_percent(
        has_reviews=has_reviews,
        has_pilot_report=has_pilot_report,
        milestones_total=milestones_total,
        milestones_complete=milestones_complete,
        completed_actions=len(completed_actions),
        total_actions=len(actions),
    )
    readiness_status = readiness_status_for(
        milestones=milestones,
        has_reviews=has_reviews,
        has_pilot_report=has_pilot_report,
        has_blockers=has_blockers,
        overdue_actions=overdue_actions,
        major_completed=major_completed,
    )
    blockers = blocker_messages(blocker_reviews, overdue_actions)
    reasons = readiness_reasons(
        readiness_status=readiness_status,
        has_reviews=has_reviews,
        has_pilot_report=has_pilot_report,
        milestones_complete=milestones_complete,
        milestones_total=milestones_total,
        overdue_count=len(overdue_actions),
        blocker_count=len(blocker_reviews),
    )
    return CustomerHealthSummary(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        tenant_slug=tenant.slug,
        pilot_progress_percent=progress,
        latest_review_date=latest_review_date,
        weekly_reviews_count=len(reviews),
        open_actions_count=len(open_actions),
        completed_actions_count=len(completed_actions),
        overdue_actions_count=len(overdue_actions),
        milestones_complete_count=milestones_complete,
        milestones_total_count=milestones_total,
        reports_generated_count=len(reports),
        latest_report_generated_at=latest_report.generated_at if latest_report else None,
        has_pilot_report=has_pilot_report,
        has_weekly_reviews=has_reviews,
        has_open_blockers=has_blockers,
        readiness_status=readiness_status,
        recommendation=recommendation_for(readiness_status),
        readiness_reasons=reasons,
        blockers=blockers,
        next_best_actions=next_best_actions_for(
            readiness_status=readiness_status,
            has_reviews=has_reviews,
            has_pilot_report=has_pilot_report,
            overdue_actions=overdue_actions,
            has_blockers=has_blockers,
            milestones_total=milestones_total,
        ),
    )


def readiness_status_for(
    *,
    milestones: list[TenantOperationalMilestone],
    has_reviews: bool,
    has_pilot_report: bool,
    has_blockers: bool,
    overdue_actions: list[TenantReviewAction],
    major_completed: set[str],
) -> str:
    if not milestones and not has_reviews:
        return "not_started"
    if has_blockers or overdue_actions:
        return "blocked"
    if has_pilot_report and has_reviews:
        return "ready_for_proposal"
    if has_reviews and major_completed:
        return "ready_for_final_review"
    return "in_progress"


def pilot_progress_percent(
    *,
    has_reviews: bool,
    has_pilot_report: bool,
    milestones_total: int,
    milestones_complete: int,
    completed_actions: int,
    total_actions: int,
) -> int:
    score = 0
    if milestones_total:
        score += min(35, round((milestones_complete / milestones_total) * 35))
    if has_reviews:
        score += 25
    if total_actions:
        score += min(20, round((completed_actions / total_actions) * 20))
    elif has_reviews:
        score += 10
    if has_pilot_report:
        score += 20
    return min(100, score)


def readiness_reasons(
    *,
    readiness_status: str,
    has_reviews: bool,
    has_pilot_report: bool,
    milestones_complete: int,
    milestones_total: int,
    overdue_count: int,
    blocker_count: int,
) -> list[str]:
    reasons = []
    if milestones_total:
        reasons.append(f"{milestones_complete}/{milestones_total} milestones are complete.")
    else:
        reasons.append("No pilot milestones have been recorded.")
    reasons.append("Weekly reviews exist." if has_reviews else "No weekly reviews recorded.")
    reasons.append("Pilot report generated." if has_pilot_report else "Pilot report not generated.")
    if overdue_count:
        reasons.append(f"{overdue_count} action(s) are overdue.")
    if blocker_count:
        reasons.append(f"{blocker_count} weekly review(s) include blockers.")
    reasons.append(f"Rule-based status: {readiness_status.replace('_', ' ')}.")
    return reasons


def blocker_messages(
    reviews: list[TenantWeeklyReview],
    overdue_actions: list[TenantReviewAction],
) -> list[str]:
    messages = [
        f"Week {review.week_number}: {review.blockers}"
        for review in reviews
        if review.blockers and review.blockers.strip()
    ]
    messages.extend(
        f"Overdue action: {action.description}"
        for action in overdue_actions
    )
    return messages


def recommendation_for(status: str) -> str:
    return {
        "not_started": (
            "Start pilot tracking by recording kickoff milestones and the first weekly review."
        ),
        "in_progress": (
            "Continue weekly reviews and close pilot actions before generating a final report."
        ),
        "blocked": "Resolve blockers or overdue actions before commercial discussion.",
        "ready_for_final_review": "Generate the pilot report and schedule final findings review.",
        "ready_for_proposal": "Prepare commercial proposal and sponsor follow-up.",
    }[status]


def next_best_actions_for(
    *,
    readiness_status: str,
    has_reviews: bool,
    has_pilot_report: bool,
    overdue_actions: list[TenantReviewAction],
    has_blockers: bool,
    milestones_total: int,
) -> list[str]:
    actions = []
    if not milestones_total:
        actions.append("Add pilot kickoff and configuration milestones.")
    if not has_reviews:
        actions.append("Create the first weekly review.")
    if overdue_actions:
        actions.append("Close or defer overdue weekly review actions.")
    if has_blockers:
        actions.append("Resolve blockers captured in weekly reviews.")
    if readiness_status == "ready_for_final_review" and not has_pilot_report:
        actions.append("Generate pilot report snapshot.")
    if readiness_status == "ready_for_proposal":
        actions.append("Draft commercial proposal using latest pilot report.")
    return actions or ["Continue weekly review cadence and keep action tracker current."]


def normalize_date(value: date) -> date:
    return value
