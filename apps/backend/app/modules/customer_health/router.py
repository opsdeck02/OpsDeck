from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_superadmin
from app.models import User
from app.modules.customer_health.schemas import CustomerHealthSummary
from app.modules.customer_health.service import customer_health_for_tenant, list_customer_health

router = APIRouter(prefix="/customer-health", tags=["customer-health"])


@router.get("/tenants", response_model=list[CustomerHealthSummary])
def read_customer_health(
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[CustomerHealthSummary]:
    return list_customer_health(db)


@router.get("/tenants/{tenant_id}", response_model=CustomerHealthSummary)
def read_customer_health_for_tenant(
    tenant_id: int,
    _: Annotated[User, Depends(require_superadmin)],
    db: Annotated[Session, Depends(get_db)],
) -> CustomerHealthSummary:
    try:
        return customer_health_for_tenant(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
