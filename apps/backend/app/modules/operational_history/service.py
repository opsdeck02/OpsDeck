from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Tenant,
    TenantOperationalMilestone,
    TenantOperationalNote,
    TenantReportSnapshot,
    TenantReviewAction,
    TenantWeeklyReview,
)
from app.modules.line_stops.service import build_historical_validation_report
from app.modules.operational_history.pdf import build_operational_history_pdf
from app.modules.operational_history.schemas import (
    MilestoneCreate,
    MilestoneUpdate,
    NoteCreate,
    NoteUpdate,
    OperationalHistorySummary,
    ReportGenerateRequest,
    TenantBasicOut,
)
from app.modules.reports.service import build_executive_continuity_report
from app.schemas.context import RequestContext

MILESTONE_STATUSES = {"pending", "complete", "blocked"}
REPORT_TYPES = {"pilot", "monthly", "executive"}


def list_milestones(db: Session, tenant_id: int) -> list[TenantOperationalMilestone]:
    ensure_tenant(db, tenant_id)
    return list(
        db.scalars(
            select(TenantOperationalMilestone)
            .where(TenantOperationalMilestone.tenant_id == tenant_id)
            .order_by(
                TenantOperationalMilestone.occurred_at.desc().nullslast(),
                TenantOperationalMilestone.created_at.desc(),
            )
        )
    )


def create_milestone(
    db: Session,
    tenant_id: int,
    payload: MilestoneCreate,
) -> TenantOperationalMilestone:
    ensure_tenant(db, tenant_id)
    status = normalize_status(payload.status)
    row = TenantOperationalMilestone(
        tenant_id=tenant_id,
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        milestone_type=payload.milestone_type.strip().lower(),
        status=status,
        occurred_at=payload.occurred_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_milestone(
    db: Session,
    tenant_id: int,
    milestone_id: int,
    payload: MilestoneUpdate,
) -> TenantOperationalMilestone:
    row = get_tenant_row(db, TenantOperationalMilestone, tenant_id, milestone_id)
    fields = payload.model_fields_set
    if "title" in fields and payload.title is not None:
        row.title = payload.title.strip()
    if "description" in fields:
        row.description = payload.description.strip() if payload.description else None
    if "milestone_type" in fields and payload.milestone_type is not None:
        row.milestone_type = payload.milestone_type.strip().lower()
    if "status" in fields and payload.status is not None:
        row.status = normalize_status(payload.status)
    if "occurred_at" in fields:
        row.occurred_at = payload.occurred_at
    db.commit()
    db.refresh(row)
    return row


def delete_milestone(db: Session, tenant_id: int, milestone_id: int) -> None:
    row = get_tenant_row(db, TenantOperationalMilestone, tenant_id, milestone_id)
    db.delete(row)
    db.commit()


def list_notes(db: Session, tenant_id: int) -> list[TenantOperationalNote]:
    ensure_tenant(db, tenant_id)
    return list(
        db.scalars(
            select(TenantOperationalNote)
            .where(TenantOperationalNote.tenant_id == tenant_id)
            .order_by(
                TenantOperationalNote.note_date.desc().nullslast(),
                TenantOperationalNote.created_at.desc(),
            )
        )
    )


def create_note(db: Session, tenant_id: int, payload: NoteCreate) -> TenantOperationalNote:
    ensure_tenant(db, tenant_id)
    row = TenantOperationalNote(
        tenant_id=tenant_id,
        note_type=payload.note_type.strip().lower(),
        title=payload.title.strip(),
        body=payload.body.strip(),
        attendees=clean_list(payload.attendees),
        actions=clean_list(payload.actions),
        note_date=payload.note_date,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_note(
    db: Session,
    tenant_id: int,
    note_id: int,
    payload: NoteUpdate,
) -> TenantOperationalNote:
    row = get_tenant_row(db, TenantOperationalNote, tenant_id, note_id)
    fields = payload.model_fields_set
    if "note_type" in fields and payload.note_type is not None:
        row.note_type = payload.note_type.strip().lower()
    if "title" in fields and payload.title is not None:
        row.title = payload.title.strip()
    if "body" in fields and payload.body is not None:
        row.body = payload.body.strip()
    if "attendees" in fields:
        row.attendees = clean_list(payload.attendees)
    if "actions" in fields:
        row.actions = clean_list(payload.actions)
    if "note_date" in fields:
        row.note_date = payload.note_date
    db.commit()
    db.refresh(row)
    return row


def delete_note(db: Session, tenant_id: int, note_id: int) -> None:
    row = get_tenant_row(db, TenantOperationalNote, tenant_id, note_id)
    db.delete(row)
    db.commit()


def list_report_snapshots(db: Session, tenant_id: int) -> list[TenantReportSnapshot]:
    ensure_tenant(db, tenant_id)
    return list(
        db.scalars(
            select(TenantReportSnapshot)
            .where(TenantReportSnapshot.tenant_id == tenant_id)
            .order_by(TenantReportSnapshot.generated_at.desc(), TenantReportSnapshot.id.desc())
        )
    )


def build_operational_history_payload(
    db: Session,
    tenant_id: int,
    report_type: str,
    period_start: date | None,
    period_end: date | None,
    *,
    title: str,
    version: int,
    generated_at: datetime,
) -> dict[str, Any]:
    tenant = ensure_tenant(db, tenant_id)
    context = RequestContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        role="tenant_admin",
        user_id=0,
    )
    milestones = list_milestones(db, tenant_id)
    notes = list_notes(db, tenant_id)
    weekly_reviews = list_weekly_reviews_for_report(db, tenant_id)
    executive = safe_executive_report(db, context)
    historical = safe_historical_report(db, context)
    summary = operational_summary_text(
        tenant,
        milestones,
        notes,
        weekly_reviews,
        executive,
        historical,
    )
    return {
        "title": title,
        "report_type": report_type,
        "version": version,
        "generated_at": generated_at.isoformat(),
        "tenant": {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "plan_tier": tenant.plan_tier,
            "is_active": tenant.is_active,
            "is_demo_tenant": tenant.is_demo_tenant,
            "created_at": tenant.created_at.isoformat(),
        },
        "period": {
            "start": period_start.isoformat() if period_start else None,
            "end": period_end.isoformat() if period_end else None,
        },
        "summary": summary,
        "milestones": [milestone_payload(item) for item in milestones],
        "notes": [note_payload(item) for item in notes],
        "weekly_reviews": weekly_reviews,
        "continuity_summary": continuity_summary(executive),
        "historical_summary": historical_summary(historical),
        "limitations": [
            "Operational history is maintained by OpsDeck superadmin users.",
            "Report snapshots preserve the state available at generation time.",
            (
                "Data quality depends on tenant-uploaded inventory, threshold, shipment, "
                "and incident records."
            ),
        ],
        "success_criteria": [
            "Pilot milestones are recorded and reviewable.",
            "Continuity risks and historical validation evidence are summarized when available.",
            "Generated report versions remain immutable for future review.",
        ],
        "next_steps": next_steps(milestones, notes, executive, historical),
    }


def generate_report_snapshot(
    db: Session,
    tenant_id: int,
    payload: ReportGenerateRequest,
    generated_by_user_id: int | None,
) -> TenantReportSnapshot:
    ensure_tenant(db, tenant_id)
    report_type = normalize_report_type(payload.report_type)
    generated_at = datetime.now(UTC)
    version = next_report_version(
        db,
        tenant_id=tenant_id,
        report_type=report_type,
        period_start=payload.period_start,
        period_end=payload.period_end,
    )
    snapshot_payload = build_operational_history_payload(
        db,
        tenant_id,
        report_type,
        payload.period_start,
        payload.period_end,
        title=payload.title.strip(),
        version=version,
        generated_at=generated_at,
    )
    pdf_bytes = build_operational_history_pdf(snapshot_payload)
    row = TenantReportSnapshot(
        tenant_id=tenant_id,
        report_type=report_type,
        period_start=payload.period_start,
        period_end=payload.period_end,
        version=version,
        title=payload.title.strip(),
        summary=snapshot_payload["summary"],
        snapshot_payload=snapshot_payload,
        pdf_bytes=pdf_bytes,
        generated_by_user_id=generated_by_user_id,
        generated_at=generated_at,
        created_at=generated_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_report_snapshot(db: Session, tenant_id: int, report_id: int) -> TenantReportSnapshot:
    return get_tenant_row(db, TenantReportSnapshot, tenant_id, report_id)


def get_report_pdf(db: Session, tenant_id: int, report_id: int) -> bytes:
    row = get_report_snapshot(db, tenant_id, report_id)
    if row.pdf_bytes is None:
        raise ValueError("Report PDF is unavailable")
    return row.pdf_bytes


def operational_history_summary(db: Session, tenant_id: int) -> OperationalHistorySummary:
    tenant = ensure_tenant(db, tenant_id)
    latest_report = db.scalar(
        select(TenantReportSnapshot)
        .where(TenantReportSnapshot.tenant_id == tenant_id)
        .order_by(TenantReportSnapshot.generated_at.desc(), TenantReportSnapshot.id.desc())
        .limit(1)
    )
    recent_milestones = list_milestones(db, tenant_id)[:5]
    recent_notes = list_notes(db, tenant_id)[:5]
    milestone_count = db.scalar(
        select(func.count(TenantOperationalMilestone.id)).where(
            TenantOperationalMilestone.tenant_id == tenant_id
        )
    )
    note_count = db.scalar(
        select(func.count(TenantOperationalNote.id)).where(
            TenantOperationalNote.tenant_id == tenant_id
        )
    )
    report_count = db.scalar(
        select(func.count(TenantReportSnapshot.id)).where(
            TenantReportSnapshot.tenant_id == tenant_id
        )
    )
    return OperationalHistorySummary(
        tenant=TenantBasicOut.model_validate(tenant, from_attributes=True),
        milestone_count=milestone_count or 0,
        note_count=note_count or 0,
        report_count=report_count or 0,
        latest_report=latest_report,
        recent_milestones=recent_milestones,
        recent_notes=recent_notes,
    )


def ensure_tenant(db: Session, tenant_id: int) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found")
    return tenant


def get_tenant_row(db: Session, model, tenant_id: int, row_id: int):
    row = db.scalar(select(model).where(model.tenant_id == tenant_id, model.id == row_id))
    if row is None:
        raise ValueError("Operational history record not found")
    return row


def normalize_status(value: str) -> str:
    status = value.strip().lower()
    if status not in MILESTONE_STATUSES:
        raise ValueError("Milestone status must be pending, complete, or blocked")
    return status


def normalize_report_type(value: str) -> str:
    report_type = value.strip().lower()
    if report_type not in REPORT_TYPES:
        raise ValueError("Report type must be pilot, monthly, or executive")
    return report_type


def clean_list(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    cleaned = [item.strip() for item in values if item and item.strip()]
    return cleaned or None


def next_report_version(
    db: Session,
    *,
    tenant_id: int,
    report_type: str,
    period_start: date | None,
    period_end: date | None,
) -> int:
    current = db.scalar(
        select(func.max(TenantReportSnapshot.version)).where(
            TenantReportSnapshot.tenant_id == tenant_id,
            TenantReportSnapshot.report_type == report_type,
            TenantReportSnapshot.period_start == period_start,
            TenantReportSnapshot.period_end == period_end,
        )
    )
    return (current or 0) + 1


def milestone_payload(row: TenantOperationalMilestone) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "description": row.description,
        "milestone_type": row.milestone_type,
        "status": row.status,
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        "created_at": row.created_at.isoformat(),
    }


def note_payload(row: TenantOperationalNote) -> dict[str, Any]:
    return {
        "id": row.id,
        "note_type": row.note_type,
        "title": row.title,
        "body": row.body,
        "attendees": row.attendees or [],
        "actions": row.actions or [],
        "note_date": row.note_date.isoformat() if row.note_date else None,
        "created_at": row.created_at.isoformat(),
    }


def safe_executive_report(db: Session, context: RequestContext):
    try:
        return build_executive_continuity_report(db, context)
    except Exception:
        return None


def safe_historical_report(db: Session, context: RequestContext):
    try:
        return build_historical_validation_report(db, context, limit=100)
    except Exception:
        return None


def operational_summary_text(
    tenant: Tenant,
    milestones: list[TenantOperationalMilestone],
    notes: list[TenantOperationalNote],
    weekly_reviews: list[dict[str, Any]],
    executive,
    historical,
) -> str:
    parts = [
        (
            f"{tenant.name} has {len(milestones)} recorded milestone(s) "
            f"and {len(notes)} review note(s). "
            f"{len(weekly_reviews)} structured weekly review(s) are captured."
        )
    ]
    if executive is not None:
        parts.append(
            "Current continuity report covers "
            f"{executive.summary.materials_assessed} material(s), including "
            f"{executive.summary.critical_materials} critical and "
            f"{executive.summary.high_risk_materials} high-risk material(s)."
        )
    if historical is not None and historical.summary is not None:
        parts.append(
            "Historical validation analyzed "
            f"{historical.summary.incidents_analyzed} incident(s) with "
            f"{historical.summary.detection_rate_percent}% detection rate."
        )
    return " ".join(parts)


def continuity_summary(executive) -> list[str]:
    if executive is None:
        return ["Executive continuity report was not available at snapshot generation time."]
    summary = executive.summary
    return [
        f"Materials assessed: {summary.materials_assessed}",
        f"Critical materials: {summary.critical_materials}",
        f"High risk materials: {summary.high_risk_materials}",
        f"Average operational trust: {summary.average_operational_trust}",
        f"Average assessment calibration: {summary.average_assessment_calibration}",
    ]


def historical_summary(historical) -> list[str]:
    if historical is None or historical.summary is None:
        return ["No historical validation summary was available at snapshot generation time."]
    summary = historical.summary
    return [
        f"Incidents analyzed: {summary.incidents_analyzed}",
        f"Detected: {summary.detected}",
        f"Partially detected: {summary.partially_detected}",
        f"Missed: {summary.missed}",
        f"Detection rate: {summary.detection_rate_percent}%",
        f"Average warning lead time: {summary.average_warning_lead_time_days or 'N/A'} days",
    ]


def list_weekly_reviews_for_report(db: Session, tenant_id: int) -> list[dict[str, Any]]:
    reviews = list(
        db.scalars(
            select(TenantWeeklyReview)
            .where(TenantWeeklyReview.tenant_id == tenant_id)
            .order_by(TenantWeeklyReview.week_number.asc(), TenantWeeklyReview.review_date.asc())
        )
    )
    return [weekly_review_payload(db, item) for item in reviews]


def weekly_review_payload(db: Session, review: TenantWeeklyReview) -> dict[str, Any]:
    actions = list(
        db.scalars(
            select(TenantReviewAction)
            .where(TenantReviewAction.weekly_review_id == review.id)
            .order_by(TenantReviewAction.id.asc())
        )
    )
    return {
        "id": review.id,
        "week_number": review.week_number,
        "review_date": review.review_date.isoformat(),
        "review_title": review.review_title,
        "attendees": review.attendees or [],
        "meeting_summary": review.meeting_summary,
        "operational_observations": review.operational_observations or [],
        "customer_feedback": review.customer_feedback,
        "blockers": review.blockers,
        "next_focus": review.next_focus,
        "actions": [
            {
                "description": action.description,
                "owner": action.owner,
                "due_date": action.due_date.isoformat() if action.due_date else None,
                "status": action.status,
            }
            for action in actions
        ],
    }


def next_steps(
    milestones: list[TenantOperationalMilestone],
    notes: list[TenantOperationalNote],
    executive,
    historical,
) -> list[str]:
    steps = []
    if any(item.status == "blocked" for item in milestones):
        steps.append("Resolve blocked pilot milestones before final review.")
    if not milestones:
        steps.append("Record kickoff, configuration, review, and final-findings milestones.")
    if not notes:
        steps.append("Add internal review notes for observations, data quality, and next steps.")
    if executive is not None and executive.summary.critical_materials:
        steps.append("Review critical material exposure with tenant sponsor.")
    if (
        historical is None
        or historical.summary is None
        or historical.summary.incidents_analyzed == 0
    ):
        steps.append("Add historical incidents to strengthen pilot evidence.")
    return steps or ["Continue monthly operational history capture and report versioning."]
