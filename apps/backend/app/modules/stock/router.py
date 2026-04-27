from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_request_context, require_operator_access
from app.modules.stock.schemas import (
    StockCoverDetailResponse,
    StockCoverSummaryResponse,
    StockRiskActionRequest,
)
from app.modules.stock.service import (
    calculate_stock_cover_detail,
    calculate_stock_cover_summary,
    update_stock_risk_action,
)
from app.schemas.context import RequestContext
from app.utils.csv_exports import build_csv_response

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/cover", response_model=StockCoverSummaryResponse)
def stock_cover_summary(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> StockCoverSummaryResponse:
    return calculate_stock_cover_summary(db, context)


@router.get("/cover/export.csv")
def export_stock_cover_summary(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
):
    summary = calculate_stock_cover_summary(db, context)
    return build_csv_response(
        filename="stock_cover_summary.csv",
        fieldnames=[
            "plant_code",
            "plant_name",
            "material_code",
            "material_name",
            "latest_snapshot_time",
            "current_stock_mt",
            "raw_inbound_pipeline_mt",
            "effective_inbound_pipeline_mt",
            "daily_consumption_mt",
            "days_of_cover",
            "threshold_days",
            "warning_days",
            "status",
            "confidence_level",
            "linked_shipment_count",
        ],
        rows=[
            {
                "plant_code": row.plant_code,
                "plant_name": row.plant_name,
                "material_code": row.material_code,
                "material_name": row.material_name,
                "latest_snapshot_time": row.latest_snapshot_time,
                "current_stock_mt": row.calculation.current_stock_mt,
                "raw_inbound_pipeline_mt": row.calculation.raw_inbound_pipeline_mt,
                "effective_inbound_pipeline_mt": (
                    row.calculation.effective_inbound_pipeline_mt
                ),
                "daily_consumption_mt": row.calculation.daily_consumption_mt,
                "days_of_cover": row.calculation.days_of_cover,
                "threshold_days": row.calculation.threshold_days,
                "warning_days": row.calculation.warning_days,
                "status": row.calculation.status,
                "confidence_level": row.calculation.confidence_level,
                "linked_shipment_count": row.calculation.linked_shipment_count,
            }
            for row in summary.rows
        ],
    )


@router.get("/cover/{plant_id}/{material_id}", response_model=StockCoverDetailResponse)
def stock_cover_detail(
    plant_id: int,
    material_id: int,
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> StockCoverDetailResponse:
    detail = calculate_stock_cover_detail(db, context, plant_id, material_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Stock cover detail not found")
    return detail


@router.patch("/cover/{plant_id}/{material_id}/action", response_model=StockCoverDetailResponse)
def stock_cover_action(
    plant_id: int,
    material_id: int,
    payload: StockRiskActionRequest,
    _: Annotated[RequestContext, Depends(require_operator_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> StockCoverDetailResponse:
    try:
        detail = update_stock_risk_action(db, context, plant_id, material_id, payload.action_status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="Stock cover detail not found")
    return detail
