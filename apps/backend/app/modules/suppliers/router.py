from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_request_context, require_admin_access
from app.modules.suppliers.schemas import (
    SupplierCreate,
    SupplierDetail,
    SupplierLinkShipmentsResponse,
    SupplierOut,
    SupplierPerformanceSummary,
    SupplierUpdate,
)
from app.modules.suppliers.service import (
    create_supplier,
    get_supplier_detail,
    link_shipments_by_supplier_name,
    list_suppliers,
    performance_summary,
    soft_delete_supplier,
    update_supplier,
)
from app.schemas.context import RequestContext

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("", response_model=list[SupplierOut])
def list_supplier_records(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SupplierOut]:
    return list_suppliers(db, context)


@router.post("", response_model=SupplierOut)
def create_supplier_record(
    payload: SupplierCreate,
    _: Annotated[RequestContext, Depends(require_admin_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> SupplierOut:
    try:
        return create_supplier(db, context, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/performance/summary", response_model=SupplierPerformanceSummary)
def supplier_performance_summary(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> SupplierPerformanceSummary:
    return performance_summary(db, context)


@router.get("/{supplier_id}", response_model=SupplierDetail)
def get_supplier_record(
    supplier_id: uuid.UUID,
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> SupplierDetail:
    supplier = get_supplier_detail(db, context, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    return supplier


@router.patch("/{supplier_id}", response_model=SupplierOut)
def update_supplier_record(
    supplier_id: uuid.UUID,
    payload: SupplierUpdate,
    _: Annotated[RequestContext, Depends(require_admin_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> SupplierOut:
    try:
        supplier = update_supplier(db, context, supplier_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    return supplier


@router.delete("/{supplier_id}", response_model=SupplierOut)
def delete_supplier_record(
    supplier_id: uuid.UUID,
    _: Annotated[RequestContext, Depends(require_admin_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> SupplierOut:
    supplier = soft_delete_supplier(db, context, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    return supplier


@router.post("/{supplier_id}/link-shipments", response_model=SupplierLinkShipmentsResponse)
def link_supplier_shipments(
    supplier_id: uuid.UUID,
    _: Annotated[RequestContext, Depends(require_admin_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> SupplierLinkShipmentsResponse:
    result = link_shipments_by_supplier_name(db, context, supplier_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    return result
