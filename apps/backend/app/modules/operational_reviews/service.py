from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    TenantOperationalMilestone,
    TenantReviewAction,
    TenantWeeklyReview,
)
from app.modules.operational_history.service import ensure_tenant
from app.modules.operational_reviews.schemas import (
    ReviewActionCreate,
    ReviewActionUpdate,
    WeeklyReviewCreate,
    WeeklyReviewOut,
    WeeklyReviewUpdate,
)

ACTION_STATUSES = {"Open", "In Progress", "Completed", "Deferred"}


def list_reviews(db: Session, tenant_id: int) -> list[WeeklyReviewOut]:
    ensure_tenant(db, tenant_id)
    reviews = list(
        db.scalars(
            select(TenantWeeklyReview)
            .where(TenantWeeklyReview.tenant_id == tenant_id)
            .order_by(TenantWeeklyReview.week_number.asc(), TenantWeeklyReview.review_date.asc())
        )
    )
    return [review_out(db, item) for item in reviews]


def create_review(
    db: Session,
    tenant_id: int,
    payload: WeeklyReviewCreate,
    created_by_user_id: int | None,
) -> WeeklyReviewOut:
    ensure_tenant(db, tenant_id)
    review = TenantWeeklyReview(
        tenant_id=tenant_id,
        week_number=payload.week_number,
        review_date=payload.review_date,
        review_title=payload.review_title.strip(),
        attendees=clean_list(payload.attendees) or [],
        meeting_summary=clean_text(payload.meeting_summary),
        operational_observations=clean_list(payload.operational_observations) or [],
        customer_feedback=clean_text(payload.customer_feedback),
        agreed_actions=[action_payload(action) for action in payload.agreed_actions],
        blockers=clean_text(payload.blockers),
        next_focus=clean_text(payload.next_focus),
        created_by_user_id=created_by_user_id,
    )
    db.add(review)
    db.flush()
    for action in payload.agreed_actions:
        db.add(action_row(review.id, action))
    add_timeline_milestone(
        db,
        tenant_id=tenant_id,
        title=f"Week {payload.week_number} Review Completed",
        description=payload.meeting_summary,
        occurred_at=payload.review_date,
    )
    db.commit()
    db.refresh(review)
    return review_out(db, review)


def update_review(
    db: Session,
    tenant_id: int,
    review_id: int,
    payload: WeeklyReviewUpdate,
) -> WeeklyReviewOut:
    review = get_review(db, tenant_id, review_id)
    fields = payload.model_fields_set
    if "week_number" in fields and payload.week_number is not None:
        review.week_number = payload.week_number
    if "review_date" in fields and payload.review_date is not None:
        review.review_date = payload.review_date
    if "review_title" in fields and payload.review_title is not None:
        review.review_title = payload.review_title.strip()
    if "attendees" in fields:
        review.attendees = clean_list(payload.attendees) or []
    if "meeting_summary" in fields:
        review.meeting_summary = clean_text(payload.meeting_summary)
    if "operational_observations" in fields:
        review.operational_observations = clean_list(payload.operational_observations) or []
    if "customer_feedback" in fields:
        review.customer_feedback = clean_text(payload.customer_feedback)
    if "blockers" in fields:
        review.blockers = clean_text(payload.blockers)
    if "next_focus" in fields:
        review.next_focus = clean_text(payload.next_focus)
    if "agreed_actions" in fields and payload.agreed_actions is not None:
        review.agreed_actions = [action_payload(action) for action in payload.agreed_actions]
        for existing in list_actions(db, tenant_id, review.id):
            db.delete(existing)
        db.flush()
        for action in payload.agreed_actions:
            db.add(action_row(review.id, action))
    db.commit()
    db.refresh(review)
    return review_out(db, review)


def delete_review(db: Session, tenant_id: int, review_id: int) -> None:
    review = get_review(db, tenant_id, review_id)
    db.delete(review)
    db.commit()


def list_actions(db: Session, tenant_id: int, review_id: int) -> list[TenantReviewAction]:
    get_review(db, tenant_id, review_id)
    return list(
        db.scalars(
            select(TenantReviewAction)
            .where(TenantReviewAction.weekly_review_id == review_id)
            .order_by(TenantReviewAction.id.asc())
        )
    )


def update_action(
    db: Session,
    tenant_id: int,
    review_id: int,
    action_id: int,
    payload: ReviewActionUpdate,
) -> TenantReviewAction:
    review = get_review(db, tenant_id, review_id)
    action = db.scalar(
        select(TenantReviewAction).where(
            TenantReviewAction.id == action_id,
            TenantReviewAction.weekly_review_id == review_id,
        )
    )
    if action is None:
        raise ValueError("Review action not found")
    previous_status = action.status
    fields = payload.model_fields_set
    if "description" in fields and payload.description is not None:
        action.description = payload.description.strip()
    if "owner" in fields:
        action.owner = clean_text(payload.owner)
    if "due_date" in fields:
        action.due_date = payload.due_date
    if "status" in fields and payload.status is not None:
        action.status = normalize_action_status(payload.status)
    if previous_status != "Completed" and action.status == "Completed":
        add_timeline_milestone(
            db,
            tenant_id=tenant_id,
            title=f"Action Completed: {action.description}",
            description=f"Completed from Week {review.week_number} Review.",
            occurred_at=review.review_date,
            milestone_type="review_action_completed",
        )
    db.commit()
    db.refresh(action)
    return action


def get_review(db: Session, tenant_id: int, review_id: int) -> TenantWeeklyReview:
    row = db.scalar(
        select(TenantWeeklyReview).where(
            TenantWeeklyReview.tenant_id == tenant_id,
            TenantWeeklyReview.id == review_id,
        )
    )
    if row is None:
        raise ValueError("Weekly review not found")
    return row


def review_out(db: Session, review: TenantWeeklyReview) -> WeeklyReviewOut:
    return WeeklyReviewOut.model_validate(
        {
            "id": review.id,
            "tenant_id": review.tenant_id,
            "week_number": review.week_number,
            "review_date": review.review_date,
            "review_title": review.review_title,
            "attendees": review.attendees or [],
            "meeting_summary": review.meeting_summary,
            "operational_observations": review.operational_observations or [],
            "customer_feedback": review.customer_feedback,
            "agreed_actions": review.agreed_actions or [],
            "blockers": review.blockers,
            "next_focus": review.next_focus,
            "created_by_user_id": review.created_by_user_id,
            "created_at": review.created_at,
            "updated_at": review.updated_at,
            "actions": list_actions(db, review.tenant_id, review.id),
        }
    )


def add_timeline_milestone(
    db: Session,
    *,
    tenant_id: int,
    title: str,
    description: str | None,
    occurred_at,
    milestone_type: str = "weekly_review",
) -> None:
    db.add(
        TenantOperationalMilestone(
            tenant_id=tenant_id,
            title=title,
            description=clean_text(description),
            milestone_type=milestone_type,
            status="complete",
            occurred_at=occurred_at,
        )
    )


def action_row(review_id: int, payload: ReviewActionCreate) -> TenantReviewAction:
    return TenantReviewAction(
        weekly_review_id=review_id,
        description=payload.description.strip(),
        owner=clean_text(payload.owner),
        due_date=payload.due_date,
        status=normalize_action_status(payload.status),
    )


def action_payload(payload: ReviewActionCreate) -> dict:
    return {
        "description": payload.description.strip(),
        "owner": clean_text(payload.owner),
        "due_date": payload.due_date.isoformat() if payload.due_date else None,
        "status": normalize_action_status(payload.status),
    }


def normalize_action_status(value: str) -> str:
    normalized = " ".join(value.strip().split()).title()
    if normalized not in ACTION_STATUSES:
        raise ValueError("Action status must be Open, In Progress, Completed, or Deferred")
    return normalized


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def clean_list(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    cleaned = [item.strip() for item in values if item and item.strip()]
    return cleaned or None
