from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_superadmin
from app.models import User
from app.modules.operational_reviews.schemas import (
    ReviewActionOut,
    ReviewActionUpdate,
    WeeklyReviewCreate,
    WeeklyReviewOut,
    WeeklyReviewUpdate,
)
from app.modules.operational_reviews.service import (
    create_review,
    delete_review,
    list_actions,
    list_reviews,
    update_action,
    update_review,
)

router = APIRouter(prefix="/operational-reviews", tags=["operational-reviews"])


@router.get("/tenants/{tenant_id}/weekly-reviews", response_model=list[WeeklyReviewOut])
def read_reviews(
    tenant_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[WeeklyReviewOut]:
    return translate_errors(lambda: list_reviews(db, tenant_id))


@router.post("/tenants/{tenant_id}/weekly-reviews", response_model=WeeklyReviewOut)
def add_review(
    tenant_id: int,
    payload: WeeklyReviewCreate,
    current_user: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> WeeklyReviewOut:
    return translate_errors(
        lambda: create_review(
            db,
            tenant_id,
            payload,
            created_by_user_id=current_user.id,
        )
    )


@router.patch(
    "/tenants/{tenant_id}/weekly-reviews/{review_id}",
    response_model=WeeklyReviewOut,
)
def patch_review(
    tenant_id: int,
    review_id: int,
    payload: WeeklyReviewUpdate,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> WeeklyReviewOut:
    return translate_errors(lambda: update_review(db, tenant_id, review_id, payload))


@router.delete(
    "/tenants/{tenant_id}/weekly-reviews/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_review(
    tenant_id: int,
    review_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    translate_errors(lambda: delete_review(db, tenant_id, review_id))


@router.get(
    "/tenants/{tenant_id}/weekly-reviews/{review_id}/actions",
    response_model=list[ReviewActionOut],
)
def read_actions(
    tenant_id: int,
    review_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ReviewActionOut]:
    return translate_errors(lambda: list_actions(db, tenant_id, review_id))


@router.patch(
    "/tenants/{tenant_id}/weekly-reviews/{review_id}/actions/{action_id}",
    response_model=ReviewActionOut,
)
def patch_action(
    tenant_id: int,
    review_id: int,
    action_id: int,
    payload: ReviewActionUpdate,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> ReviewActionOut:
    return translate_errors(lambda: update_action(db, tenant_id, review_id, action_id, payload))


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
