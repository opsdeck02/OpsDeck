from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_request_context, require_admin_access
from app.modules.dashboard.service import build_executive_dashboard, build_pilot_readiness
from app.modules.stock.service import calculate_stock_cover_summary
from app.schemas.context import RequestContext
from app.schemas.dashboard import (
    DashboardMetric,
    DashboardSnapshot,
    ExecutiveDashboardResponse,
    PilotReadinessResponse,
)
from app.utils.csv_exports import build_csv_response

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/snapshot", response_model=DashboardSnapshot)
def get_dashboard_snapshot(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> DashboardSnapshot:
    summary = calculate_stock_cover_summary(db, context)
    tracked = summary.total_combinations
    avg_cover = average_cover(summary.rows)
    return DashboardSnapshot(
        tenant=context.tenant_slug,
        metrics=[
            DashboardMetric(
                label="Tracked Combos",
                value=str(tracked),
                trend="plant/material pairs",
            ),
            DashboardMetric(
                label="Critical Risks",
                value=str(summary.critical_risks),
                trend="below critical threshold",
            ),
            DashboardMetric(
                label="Warnings",
                value=str(summary.warnings),
                trend="approaching threshold",
            ),
            DashboardMetric(
                label="Average Cover",
                value=f"{avg_cover} days",
                trend="across calculable records",
            ),
        ],
        critical_risks=summary.critical_risks,
        warnings=summary.warnings,
        insufficient_data=summary.insufficient_data,
    )


@router.get("/executive", response_model=ExecutiveDashboardResponse)
def get_executive_dashboard(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> ExecutiveDashboardResponse:
    return build_executive_dashboard(db, context)


@router.get("/executive/export.csv")
def export_executive_dashboard(
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
):
    executive = build_executive_dashboard(db, context)
    rows: list[dict[str, object | None]] = [
        {
            "section": "kpi",
            "label": "tracked_combinations",
            "value": executive.kpis.tracked_combinations,
            "status": None,
            "confidence": None,
            "linked_href": None,
            "last_updated_at": executive.stock_freshness.last_updated_at,
        },
        {
            "section": "kpi",
            "label": "critical_risks",
            "value": executive.kpis.critical_risks,
            "status": "critical",
            "confidence": None,
            "linked_href": None,
            "last_updated_at": executive.stock_freshness.last_updated_at,
        },
        {
            "section": "kpi",
            "label": "warning_risks",
            "value": executive.kpis.warning_risks,
            "status": "warning",
            "confidence": None,
            "linked_href": None,
            "last_updated_at": executive.stock_freshness.last_updated_at,
        },
        {
            "section": "kpi",
            "label": "open_exceptions",
            "value": executive.kpis.open_exceptions,
            "status": "open",
            "confidence": None,
            "linked_href": None,
            "last_updated_at": executive.exception_freshness.last_updated_at,
        },
        {
            "section": "kpi",
            "label": "unassigned_exceptions",
            "value": executive.kpis.unassigned_exceptions,
            "status": "open",
            "confidence": None,
            "linked_href": None,
            "last_updated_at": executive.exception_freshness.last_updated_at,
        },
    ]
    rows.extend(
        {
            "section": "top_risk",
            "label": f"{item.plant_name} / {item.material_name}",
            "value": item.days_of_cover,
            "status": item.status,
            "confidence": item.confidence,
            "linked_href": f"/dashboard/stock-cover/{item.plant_id}/{item.material_id}",
            "last_updated_at": executive.stock_freshness.last_updated_at,
        }
        for item in executive.top_risks
    )
    rows.extend(
        {
            "section": "exception",
            "label": item.title,
            "value": item.owner_name,
            "status": item.status,
            "confidence": item.severity,
            "linked_href": f"/dashboard/exceptions/{item.id}",
            "last_updated_at": item.updated_at,
        }
        for item in executive.critical_open_exceptions
    )
    rows.extend(
        {
            "section": "movement",
            "label": item.shipment_id,
            "value": item.issue_label,
            "status": item.freshness_label,
            "confidence": item.confidence,
            "linked_href": f"/dashboard/shipments/{item.shipment_id}",
            "last_updated_at": executive.movement_freshness.last_updated_at,
        }
        for item in (
            executive.stale_movement_shipments
            + executive.low_confidence_shipments
            + executive.likely_delayed_shipments
        )
    )
    rows.extend(
        {
            "section": "attention",
            "label": item.description,
            "value": item.current_owner,
            "status": item.kind,
            "confidence": None,
            "linked_href": item.href,
            "last_updated_at": None,
        }
        for item in executive.needs_attention
    )
    return build_csv_response(
        filename="executive_dashboard.csv",
        fieldnames=[
            "section",
            "label",
            "value",
            "status",
            "confidence",
            "linked_href",
            "last_updated_at",
        ],
        rows=rows,
    )


@router.get("/pilot-readiness", response_model=PilotReadinessResponse)
def get_pilot_readiness(
    _: Annotated[RequestContext, Depends(require_admin_access)],
    context: Annotated[RequestContext, Depends(get_request_context)],
    db: Annotated[Session, Depends(get_db)],
) -> PilotReadinessResponse:
    return build_pilot_readiness(db, context)


def average_cover(rows: list) -> str:
    cover_values = [
        row.calculation.days_of_cover
        for row in rows
        if row.calculation.days_of_cover is not None
    ]
    if not cover_values:
        return "0.00"
    average = sum(cover_values, start=Decimal("0")) / Decimal(len(cover_values))
    return f"{average.quantize(Decimal('0.01'))}"
