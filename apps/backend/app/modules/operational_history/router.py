from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_superadmin
from app.models import User
from app.modules.operational_history.schemas import (
    MilestoneCreate,
    MilestoneOut,
    MilestoneUpdate,
    NoteCreate,
    NoteOut,
    NoteUpdate,
    OperationalHistorySummary,
    ReportGenerateRequest,
    ReportSnapshotOut,
)
from app.modules.operational_history.service import (
    create_milestone,
    create_note,
    delete_milestone,
    delete_note,
    generate_report_snapshot,
    get_report_pdf,
    get_report_snapshot,
    list_milestones,
    list_notes,
    list_report_snapshots,
    operational_history_summary,
    update_milestone,
    update_note,
)

router = APIRouter(prefix="/operational-history", tags=["operational-history"])


@router.get("/tenants/{tenant_id}", response_model=OperationalHistorySummary)
def read_operational_history_summary(
    tenant_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> OperationalHistorySummary:
    return translate_errors(lambda: operational_history_summary(db, tenant_id))


@router.get("/tenants/{tenant_id}/milestones", response_model=list[MilestoneOut])
def read_milestones(
    tenant_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[MilestoneOut]:
    return translate_errors(lambda: list_milestones(db, tenant_id))


@router.post("/tenants/{tenant_id}/milestones", response_model=MilestoneOut)
def add_milestone(
    tenant_id: int,
    payload: MilestoneCreate,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> MilestoneOut:
    return translate_errors(lambda: create_milestone(db, tenant_id, payload))


@router.patch("/tenants/{tenant_id}/milestones/{milestone_id}", response_model=MilestoneOut)
def patch_milestone(
    tenant_id: int,
    milestone_id: int,
    payload: MilestoneUpdate,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> MilestoneOut:
    return translate_errors(lambda: update_milestone(db, tenant_id, milestone_id, payload))


@router.delete(
    "/tenants/{tenant_id}/milestones/{milestone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_milestone(
    tenant_id: int,
    milestone_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    translate_errors(lambda: delete_milestone(db, tenant_id, milestone_id))


@router.get("/tenants/{tenant_id}/notes", response_model=list[NoteOut])
def read_notes(
    tenant_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[NoteOut]:
    return translate_errors(lambda: list_notes(db, tenant_id))


@router.post("/tenants/{tenant_id}/notes", response_model=NoteOut)
def add_note(
    tenant_id: int,
    payload: NoteCreate,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> NoteOut:
    return translate_errors(lambda: create_note(db, tenant_id, payload))


@router.patch("/tenants/{tenant_id}/notes/{note_id}", response_model=NoteOut)
def patch_note(
    tenant_id: int,
    note_id: int,
    payload: NoteUpdate,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> NoteOut:
    return translate_errors(lambda: update_note(db, tenant_id, note_id, payload))


@router.delete("/tenants/{tenant_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_note(
    tenant_id: int,
    note_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    translate_errors(lambda: delete_note(db, tenant_id, note_id))


@router.get("/tenants/{tenant_id}/reports", response_model=list[ReportSnapshotOut])
def read_reports(
    tenant_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ReportSnapshotOut]:
    return translate_errors(lambda: list_report_snapshots(db, tenant_id))


@router.post("/tenants/{tenant_id}/reports/generate", response_model=ReportSnapshotOut)
def generate_report(
    tenant_id: int,
    payload: ReportGenerateRequest,
    current_user: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> ReportSnapshotOut:
    return translate_errors(
        lambda: generate_report_snapshot(
            db,
            tenant_id,
            payload,
            generated_by_user_id=current_user.id,
        )
    )


@router.get("/tenants/{tenant_id}/reports/{report_id}", response_model=ReportSnapshotOut)
def read_report(
    tenant_id: int,
    report_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> ReportSnapshotOut:
    return translate_errors(lambda: get_report_snapshot(db, tenant_id, report_id))


@router.get("/tenants/{tenant_id}/reports/{report_id}/pdf")
def download_report_pdf(
    tenant_id: int,
    report_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    pdf = translate_errors(lambda: get_report_pdf(db, tenant_id, report_id))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="tenant-{tenant_id}-operational-history-{report_id}.pdf"'
            )
        },
    )


def translate_errors(operation):
    try:
        return operation()
    except ValueError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
