from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_admin_access
from app.models import Material, Plant, ProductionInterruptionImpactConfig, ProductionLine
from app.modules.impact.production_interruption import get_active_interruption_config
from app.modules.impact.schemas import (
    ProductionInterruptionImpactConfigPayload,
    ProductionInterruptionImpactConfigRead,
)
from app.schemas.context import RequestContext

router = APIRouter(prefix="/impact", tags=["impact"])


@router.get(
    "/interruption-config",
    response_model=ProductionInterruptionImpactConfigRead | None,
)
def get_interruption_config(
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
    plant_id: Annotated[int, Query()],
    material_id: Annotated[int, Query()],
    production_line_id: Annotated[int | None, Query()] = None,
) -> ProductionInterruptionImpactConfigRead | None:
    ensure_context(db, context, plant_id, material_id, production_line_id)
    config = get_active_interruption_config(
        db,
        tenant_id=context.tenant_id,
        plant_id=plant_id,
        material_id=material_id,
        production_line_id=production_line_id,
    )
    return (
        ProductionInterruptionImpactConfigRead.model_validate(config)
        if config is not None
        else None
    )


@router.put(
    "/interruption-config",
    response_model=ProductionInterruptionImpactConfigRead,
)
def upsert_interruption_config(
    payload: ProductionInterruptionImpactConfigPayload,
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> ProductionInterruptionImpactConfigRead:
    ensure_context(
        db,
        context,
        payload.plant_id,
        payload.material_id,
        payload.production_line_id,
    )
    config = db.scalar(
        select(ProductionInterruptionImpactConfig).where(
            ProductionInterruptionImpactConfig.tenant_id == context.tenant_id,
            ProductionInterruptionImpactConfig.plant_id == payload.plant_id,
            ProductionInterruptionImpactConfig.material_id == payload.material_id,
            ProductionInterruptionImpactConfig.production_line_id == payload.production_line_id,
        )
    )
    if config is None:
        config = ProductionInterruptionImpactConfig(
            tenant_id=context.tenant_id,
            plant_id=payload.plant_id,
            material_id=payload.material_id,
            production_line_id=payload.production_line_id,
        )
        db.add(config)

    config.production_rate_mt_per_hour = payload.production_rate_mt_per_hour
    config.finished_goods_value_per_mt = payload.finished_goods_value_per_mt
    config.survivable_hours_without_material = payload.survivable_hours_without_material
    config.line_dependency_ratio = payload.line_dependency_ratio
    config.downtime_cost_per_hour = payload.downtime_cost_per_hour
    config.restart_cost = payload.restart_cost
    config.restart_time_hours = payload.restart_time_hours
    config.substitution_factor = payload.substitution_factor
    config.cascading_impact_factor = payload.cascading_impact_factor
    config.interruption_probability_override = payload.interruption_probability_override
    config.currency = payload.currency.upper()
    config.is_active = payload.is_active
    db.commit()
    db.refresh(config)
    return ProductionInterruptionImpactConfigRead.model_validate(config)


def ensure_context(
    db: Session,
    context: RequestContext,
    plant_id: int,
    material_id: int,
    production_line_id: int | None,
) -> None:
    plant = db.scalar(
        select(Plant).where(Plant.tenant_id == context.tenant_id, Plant.id == plant_id)
    )
    material = db.scalar(
        select(Material).where(
            Material.tenant_id == context.tenant_id,
            Material.id == material_id,
        )
    )
    if plant is None or material is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plant or material was not found for this tenant.",
        )
    if production_line_id is None:
        return
    line = db.scalar(
        select(ProductionLine).where(
            ProductionLine.tenant_id == context.tenant_id,
            ProductionLine.plant_id == plant_id,
            ProductionLine.id == production_line_id,
        )
    )
    if line is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Production line was not found for this tenant plant.",
        )
