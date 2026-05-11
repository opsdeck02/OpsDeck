from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_request_context
from app.modules.reports.service import build_daily_continuity_brief_pdf, daily_brief_filename
from app.schemas.context import RequestContext

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/daily-continuity-brief")
def daily_continuity_brief(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    pdf = build_daily_continuity_brief_pdf(db, context)
    filename = daily_brief_filename()
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )

