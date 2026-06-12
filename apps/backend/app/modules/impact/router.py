from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_admin_access
from app.models import (
    Material,
    MaterialProcessDependency,
    Plant,
    PlantMaterialThreshold,
    ProcessProductDependency,
    ProductionInterruptionImpactConfig,
    ProductionLine,
    ShipmentInboundTrustConfig,
)
from app.modules.impact.configuration_validation import (
    ConfigurationValidationResult,
    validate_operational_configuration,
)
from app.modules.impact.production_interruption import get_active_interruption_config
from app.modules.impact.schemas import (
    ContinuityThresholdPayload,
    ContinuityThresholdRead,
    MaterialProcessDependencyPayload,
    MaterialProcessDependencyRead,
    ProcessProductDependencyPayload,
    ProcessProductDependencyRead,
    ProductionInterruptionImpactConfigPayload,
    ProductionInterruptionImpactConfigRead,
    ProductionLinePayload,
    ProductionLineRead,
    ShipmentInboundTrustConfigPayload,
    ShipmentInboundTrustConfigRead,
)
from app.modules.impact.shipment_inbound_trust import (
    get_active_shipment_inbound_trust_config,
)
from app.modules.signal_engine.candidate_cache import invalidate_signal_candidate_cache
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
    invalidate_signal_candidate_cache(context.tenant_id)
    db.refresh(config)
    return ProductionInterruptionImpactConfigRead.model_validate(config)


@router.get(
    "/continuity-thresholds",
    response_model=ContinuityThresholdRead | None,
)
def get_continuity_threshold(
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
    plant_id: Annotated[int, Query()],
    material_id: Annotated[int, Query()],
) -> ContinuityThresholdRead | None:
    ensure_context(db, context, plant_id, material_id, None)
    threshold = db.scalar(
        select(PlantMaterialThreshold).where(
            PlantMaterialThreshold.tenant_id == context.tenant_id,
            PlantMaterialThreshold.plant_id == plant_id,
            PlantMaterialThreshold.material_id == material_id,
        )
    )
    return ContinuityThresholdRead.model_validate(threshold) if threshold is not None else None


@router.put(
    "/continuity-thresholds",
    response_model=ContinuityThresholdRead,
)
def upsert_continuity_threshold(
    payload: ContinuityThresholdPayload,
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> ContinuityThresholdRead:
    ensure_context(db, context, payload.plant_id, payload.material_id, None)
    threshold = db.scalar(
        select(PlantMaterialThreshold).where(
            PlantMaterialThreshold.tenant_id == context.tenant_id,
            PlantMaterialThreshold.plant_id == payload.plant_id,
            PlantMaterialThreshold.material_id == payload.material_id,
        )
    )
    if threshold is None:
        threshold = PlantMaterialThreshold(
            tenant_id=context.tenant_id,
            plant_id=payload.plant_id,
            material_id=payload.material_id,
            threshold_days=payload.threshold_days,
            warning_days=payload.warning_days,
        )
        db.add(threshold)

    threshold.threshold_days = payload.threshold_days
    threshold.warning_days = payload.warning_days
    threshold.minimum_buffer_stock_days = payload.minimum_buffer_stock_days
    threshold.minimum_buffer_stock_mt = payload.minimum_buffer_stock_mt
    threshold.reserve_quantity_mt = payload.reserve_quantity_mt
    threshold.quality_hold_quantity_mt = payload.quality_hold_quantity_mt
    threshold.stockout_alert_horizon_days = payload.stockout_alert_horizon_days
    db.commit()
    invalidate_signal_candidate_cache(context.tenant_id)
    db.refresh(threshold)
    return ContinuityThresholdRead.model_validate(threshold)


@router.get(
    "/shipment-inbound-trust",
    response_model=ShipmentInboundTrustConfigRead | None,
)
def get_shipment_inbound_trust_config(
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
    plant_id: Annotated[int, Query()],
    material_id: Annotated[int, Query()],
) -> ShipmentInboundTrustConfigRead | None:
    ensure_context(db, context, plant_id, material_id, None)
    config = get_active_shipment_inbound_trust_config(
        db,
        tenant_id=context.tenant_id,
        plant_id=plant_id,
        material_id=material_id,
    )
    return ShipmentInboundTrustConfigRead.model_validate(config) if config is not None else None


@router.put(
    "/shipment-inbound-trust",
    response_model=ShipmentInboundTrustConfigRead,
)
def upsert_shipment_inbound_trust_config(
    payload: ShipmentInboundTrustConfigPayload,
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> ShipmentInboundTrustConfigRead:
    ensure_context(db, context, payload.plant_id, payload.material_id, None)
    config = db.scalar(
        select(ShipmentInboundTrustConfig).where(
            ShipmentInboundTrustConfig.tenant_id == context.tenant_id,
            ShipmentInboundTrustConfig.plant_id == payload.plant_id,
            ShipmentInboundTrustConfig.material_id == payload.material_id,
        )
    )
    if config is None:
        config = ShipmentInboundTrustConfig(
            tenant_id=context.tenant_id,
            plant_id=payload.plant_id,
            material_id=payload.material_id,
        )
        db.add(config)

    config.visibility_profile = payload.visibility_profile
    config.expected_visibility_cadence_hours = payload.expected_visibility_cadence_hours
    config.eta_drift_tolerance_hours = payload.eta_drift_tolerance_hours
    config.weak_visibility_threshold = payload.weak_visibility_threshold
    config.minimum_trusted_inbound_ratio = payload.minimum_trusted_inbound_ratio
    config.allow_unverified_inbound_protection = payload.allow_unverified_inbound_protection
    config.is_active = payload.is_active
    db.commit()
    invalidate_signal_candidate_cache(context.tenant_id)
    db.refresh(config)
    return ShipmentInboundTrustConfigRead.model_validate(config)


@router.get(
    "/configuration-validation",
    response_model=ConfigurationValidationResult,
)
def get_configuration_validation(
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
    plant_id: Annotated[int, Query()],
    material_id: Annotated[int, Query()],
) -> ConfigurationValidationResult:
    ensure_context(db, context, plant_id, material_id, None)
    return validate_operational_configuration(
        db,
        tenant_id=context.tenant_id,
        plant_id=plant_id,
        material_id=material_id,
    )


@router.get(
    "/production-lines",
    response_model=list[ProductionLineRead],
)
def list_production_lines(
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
    plant_id: Annotated[int | None, Query()] = None,
) -> list[ProductionLineRead]:
    query = select(ProductionLine).where(ProductionLine.tenant_id == context.tenant_id)
    if plant_id is not None:
        ensure_plant(db, context, plant_id)
        query = query.where(ProductionLine.plant_id == plant_id)
    lines = db.scalars(query.order_by(ProductionLine.plant_id, ProductionLine.code)).all()
    return [ProductionLineRead.model_validate(line) for line in lines]


@router.post(
    "/production-lines",
    response_model=ProductionLineRead,
    status_code=status.HTTP_201_CREATED,
)
def create_production_line(
    payload: ProductionLinePayload,
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> ProductionLineRead:
    ensure_plant(db, context, payload.plant_id)
    line = ProductionLine(
        tenant_id=context.tenant_id,
        plant_id=payload.plant_id,
        code=payload.code.strip(),
        name=payload.name.strip(),
        is_active=payload.is_active,
    )
    db.add(line)
    db.commit()
    invalidate_signal_candidate_cache(context.tenant_id)
    db.refresh(line)
    return ProductionLineRead.model_validate(line)


@router.put(
    "/production-lines/{line_id}",
    response_model=ProductionLineRead,
)
def update_production_line(
    line_id: int,
    payload: ProductionLinePayload,
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> ProductionLineRead:
    line = ensure_production_line(db, context, line_id)
    ensure_plant(db, context, payload.plant_id)
    line.plant_id = payload.plant_id
    line.code = payload.code.strip()
    line.name = payload.name.strip()
    line.is_active = payload.is_active
    db.commit()
    invalidate_signal_candidate_cache(context.tenant_id)
    db.refresh(line)
    return ProductionLineRead.model_validate(line)


@router.get(
    "/process-product-dependencies",
    response_model=list[ProcessProductDependencyRead],
)
def list_process_product_dependencies(
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
    process_id: Annotated[int | None, Query()] = None,
) -> list[ProcessProductDependencyRead]:
    query = select(ProcessProductDependency).where(
        ProcessProductDependency.tenant_id == context.tenant_id
    )
    if process_id is not None:
        ensure_production_line(db, context, process_id)
        query = query.where(ProcessProductDependency.process_id == process_id)
    rows = db.scalars(
        query.order_by(
            ProcessProductDependency.process_id,
            ProcessProductDependency.product_name,
        )
    ).all()
    return [ProcessProductDependencyRead.model_validate(row) for row in rows]


@router.post(
    "/process-product-dependencies",
    response_model=ProcessProductDependencyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_process_product_dependency(
    payload: ProcessProductDependencyPayload,
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> ProcessProductDependencyRead:
    ensure_production_line(db, context, payload.process_id)
    ensure_no_active_process_product_duplicate(db, context, payload)
    row = ProcessProductDependency(
        tenant_id=context.tenant_id,
        process_id=payload.process_id,
        product_name=payload.product_name.strip(),
        output_share_ratio=payload.output_share_ratio,
        product_value_per_mt=payload.product_value_per_mt,
        operational_criticality_factor=payload.operational_criticality_factor,
        is_active=payload.is_active,
    )
    db.add(row)
    db.commit()
    invalidate_signal_candidate_cache(context.tenant_id)
    db.refresh(row)
    return ProcessProductDependencyRead.model_validate(row)


@router.put(
    "/process-product-dependencies/{dependency_id}",
    response_model=ProcessProductDependencyRead,
)
def update_process_product_dependency(
    dependency_id: int,
    payload: ProcessProductDependencyPayload,
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> ProcessProductDependencyRead:
    row = ensure_process_product_dependency(db, context, dependency_id)
    ensure_production_line(db, context, payload.process_id)
    ensure_no_active_process_product_duplicate(db, context, payload, exclude_id=row.id)
    row.process_id = payload.process_id
    row.product_name = payload.product_name.strip()
    row.output_share_ratio = payload.output_share_ratio
    row.product_value_per_mt = payload.product_value_per_mt
    row.operational_criticality_factor = payload.operational_criticality_factor
    row.is_active = payload.is_active
    db.commit()
    invalidate_signal_candidate_cache(context.tenant_id)
    db.refresh(row)
    return ProcessProductDependencyRead.model_validate(row)


@router.delete(
    "/process-product-dependencies/{dependency_id}",
    response_model=ProcessProductDependencyRead,
)
def deactivate_process_product_dependency(
    dependency_id: int,
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> ProcessProductDependencyRead:
    row = ensure_process_product_dependency(db, context, dependency_id)
    row.is_active = False
    db.commit()
    invalidate_signal_candidate_cache(context.tenant_id)
    db.refresh(row)
    return ProcessProductDependencyRead.model_validate(row)


@router.get(
    "/material-process-dependencies",
    response_model=list[MaterialProcessDependencyRead],
)
def list_material_process_dependencies(
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
    material_id: Annotated[int | None, Query()] = None,
    process_id: Annotated[int | None, Query()] = None,
    plant_id: Annotated[int | None, Query()] = None,
) -> list[MaterialProcessDependencyRead]:
    query = select(MaterialProcessDependency).where(
        MaterialProcessDependency.tenant_id == context.tenant_id
    )
    if material_id is not None:
        ensure_material(db, context, material_id)
        query = query.where(MaterialProcessDependency.material_id == material_id)
    if process_id is not None:
        ensure_production_line(db, context, process_id)
        query = query.where(MaterialProcessDependency.process_id == process_id)
    if plant_id is not None:
        ensure_plant(db, context, plant_id)
        query = query.join(
            ProductionLine,
            ProductionLine.id == MaterialProcessDependency.process_id,
        ).where(ProductionLine.plant_id == plant_id)
    rows = db.scalars(
        query.order_by(
            MaterialProcessDependency.material_id,
            MaterialProcessDependency.process_id,
        )
    ).all()
    return [MaterialProcessDependencyRead.model_validate(row) for row in rows]


@router.post(
    "/material-process-dependencies",
    response_model=MaterialProcessDependencyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_material_process_dependency(
    payload: MaterialProcessDependencyPayload,
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> MaterialProcessDependencyRead:
    ensure_material(db, context, payload.material_id)
    ensure_production_line(db, context, payload.process_id)
    ensure_no_active_material_process_duplicate(db, context, payload)
    row = MaterialProcessDependency(
        tenant_id=context.tenant_id,
        material_id=payload.material_id,
        process_id=payload.process_id,
        dependency_ratio=payload.dependency_ratio,
        substitution_factor=payload.substitution_factor,
        survivability_hours=payload.survivability_hours,
        is_active=payload.is_active,
    )
    db.add(row)
    db.commit()
    invalidate_signal_candidate_cache(context.tenant_id)
    db.refresh(row)
    return MaterialProcessDependencyRead.model_validate(row)


@router.put(
    "/material-process-dependencies/{dependency_id}",
    response_model=MaterialProcessDependencyRead,
)
def update_material_process_dependency(
    dependency_id: int,
    payload: MaterialProcessDependencyPayload,
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> MaterialProcessDependencyRead:
    row = ensure_material_process_dependency(db, context, dependency_id)
    ensure_material(db, context, payload.material_id)
    ensure_production_line(db, context, payload.process_id)
    ensure_no_active_material_process_duplicate(db, context, payload, exclude_id=row.id)
    row.material_id = payload.material_id
    row.process_id = payload.process_id
    row.dependency_ratio = payload.dependency_ratio
    row.substitution_factor = payload.substitution_factor
    row.survivability_hours = payload.survivability_hours
    row.is_active = payload.is_active
    db.commit()
    invalidate_signal_candidate_cache(context.tenant_id)
    db.refresh(row)
    return MaterialProcessDependencyRead.model_validate(row)


@router.delete(
    "/material-process-dependencies/{dependency_id}",
    response_model=MaterialProcessDependencyRead,
)
def deactivate_material_process_dependency(
    dependency_id: int,
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> MaterialProcessDependencyRead:
    row = ensure_material_process_dependency(db, context, dependency_id)
    row.is_active = False
    db.commit()
    invalidate_signal_candidate_cache(context.tenant_id)
    db.refresh(row)
    return MaterialProcessDependencyRead.model_validate(row)


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


def ensure_plant(db: Session, context: RequestContext, plant_id: int) -> Plant:
    plant = db.scalar(
        select(Plant).where(Plant.tenant_id == context.tenant_id, Plant.id == plant_id)
    )
    if plant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plant was not found for this tenant.",
        )
    return plant


def ensure_material(db: Session, context: RequestContext, material_id: int) -> Material:
    material = db.scalar(
        select(Material).where(
            Material.tenant_id == context.tenant_id,
            Material.id == material_id,
        )
    )
    if material is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material was not found for this tenant.",
        )
    return material


def ensure_production_line(
    db: Session,
    context: RequestContext,
    line_id: int,
) -> ProductionLine:
    line = db.scalar(
        select(ProductionLine).where(
            ProductionLine.tenant_id == context.tenant_id,
            ProductionLine.id == line_id,
        )
    )
    if line is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Production line was not found for this tenant.",
        )
    return line


def ensure_no_active_process_product_duplicate(
    db: Session,
    context: RequestContext,
    payload: ProcessProductDependencyPayload,
    *,
    exclude_id: int | None = None,
) -> None:
    if not payload.is_active:
        return
    query = select(ProcessProductDependency.id).where(
        ProcessProductDependency.tenant_id == context.tenant_id,
        ProcessProductDependency.process_id == payload.process_id,
        ProcessProductDependency.is_active.is_(True),
        func.lower(ProcessProductDependency.product_name) == payload.product_name.strip().lower(),
    )
    if exclude_id is not None:
        query = query.where(ProcessProductDependency.id != exclude_id)
    if db.scalar(query) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active product mix row already exists for this process and product.",
        )


def ensure_no_active_material_process_duplicate(
    db: Session,
    context: RequestContext,
    payload: MaterialProcessDependencyPayload,
    *,
    exclude_id: int | None = None,
) -> None:
    if not payload.is_active:
        return
    query = select(MaterialProcessDependency.id).where(
        MaterialProcessDependency.tenant_id == context.tenant_id,
        MaterialProcessDependency.material_id == payload.material_id,
        MaterialProcessDependency.process_id == payload.process_id,
        MaterialProcessDependency.is_active.is_(True),
    )
    if exclude_id is not None:
        query = query.where(MaterialProcessDependency.id != exclude_id)
    if db.scalar(query) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active material dependency already exists for this material and process.",
        )


def ensure_process_product_dependency(
    db: Session,
    context: RequestContext,
    dependency_id: int,
) -> ProcessProductDependency:
    row = db.scalar(
        select(ProcessProductDependency).where(
            ProcessProductDependency.tenant_id == context.tenant_id,
            ProcessProductDependency.id == dependency_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Process product dependency was not found for this tenant.",
        )
    return row


def ensure_material_process_dependency(
    db: Session,
    context: RequestContext,
    dependency_id: int,
) -> MaterialProcessDependency:
    row = db.scalar(
        select(MaterialProcessDependency).where(
            MaterialProcessDependency.tenant_id == context.tenant_id,
            MaterialProcessDependency.id == dependency_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material process dependency was not found for this tenant.",
        )
    return row
