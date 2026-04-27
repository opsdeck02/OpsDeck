from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ExceptionCase,
    Material,
    Plant,
    PlantMaterialThreshold,
    Shipment,
    StockSnapshot,
    TenantMembership,
    User,
)
from app.models.enums import ExceptionSeverity, ExceptionStatus, ExceptionType, ShipmentState
from app.modules.shipments.confidence import assess_freshness, ensure_utc
from app.modules.impact.engine import calculate_impact
from app.modules.recommendations.engine import RecommendationSignal, recommend_action
from app.modules.shipments.movement import (
    build_context as build_movement_context,
)
from app.modules.shipments.movement import (
    build_inland_summary,
    build_port_summary,
)
from app.modules.shipments.service import build_shipment_item
from app.modules.stock.schemas import (
    ShipmentContribution,
    StockCoverBreakdown,
    StockCoverDetailResponse,
    StockCoverRow,
    StockCoverSummaryResponse,
)
from app.schemas.context import RequestContext

ACTIVE_SHIPMENT_STATES = {
    ShipmentState.PLANNED,
    ShipmentState.IN_TRANSIT,
    ShipmentState.AT_PORT,
    ShipmentState.DISCHARGING,
    ShipmentState.INLAND_TRANSIT,
    ShipmentState.DELAYED,
}

STATE_FACTORS = {
    "planned": Decimal("0.20"),
    "on_water": Decimal("0.35"),
    "at_port": Decimal("0.60"),
    "discharging": Decimal("0.80"),
    "in_transit": Decimal("0.90"),
    "delivered": Decimal("0.00"),
    "cancelled": Decimal("0.00"),
}

CONFIDENCE_FACTORS = {
    "high": Decimal("1.00"),
    "medium": Decimal("0.85"),
    "low": Decimal("0.60"),
}

FRESHNESS_FACTORS = {
    "fresh": Decimal("1.00"),
    "aging": Decimal("0.90"),
    "stale": Decimal("0.70"),
    "unknown": Decimal("0.80"),
}


@dataclass(frozen=True)
class ComboKey:
    plant_id: int
    material_id: int


@dataclass(frozen=True)
class WeightedShipment:
    shipment: Shipment
    shipment_state: str
    confidence: str
    freshness_label: str
    raw_quantity_mt: Decimal
    contribution_factor: Decimal
    effective_quantity_mt: Decimal
    explanation: str


@dataclass(frozen=True)
class ActionState:
    action_status: str
    action_sla_breach: bool
    action_age_hours: Decimal | None
    current_owner: str | None
    exception_id: int | None


def calculate_stock_cover_summary(
    db: Session,
    context: RequestContext,
) -> StockCoverSummaryResponse:
    rows = build_stock_cover_rows(db, context)
    return StockCoverSummaryResponse(
        total_combinations=len(rows),
        critical_risks=sum(1 for row in rows if row.calculation.status == "critical"),
        warnings=sum(1 for row in rows if row.calculation.status == "warning"),
        insufficient_data=sum(1 for row in rows if row.calculation.status == "insufficient_data"),
        rows=rows,
    )


def calculate_stock_cover_detail(
    db: Session,
    context: RequestContext,
    plant_id: int,
    material_id: int,
) -> StockCoverDetailResponse | None:
    rows = build_stock_cover_rows(db, context)
    target = next(
        (row for row in rows if row.plant_id == plant_id and row.material_id == material_id),
        None,
    )
    if target is None:
        return None

    shipments = weighted_shipments(db, context.tenant_id).get(ComboKey(plant_id, material_id), [])
    reasons = confidence_reasons(target, shipments)
    impact_explanation = impact_explanation_for(target.calculation)
    assumptions = [
        (
            "Inbound pipeline uses deterministic shipment-state weighting instead of a raw "
            "active total."
        ),
        "Delivered and cancelled shipments are excluded from inbound protection.",
        "Low-confidence or stale movement signals reduce effective inbound protection.",
    ]
    return StockCoverDetailResponse(
        row=target,
        shipments=[
            ShipmentContribution(
                id=item.shipment.id,
                shipment_id=item.shipment.shipment_id,
                supplier_name=item.shipment.supplier_name,
                raw_quantity_mt=quantize_decimal(item.raw_quantity_mt),
                effective_quantity_mt=quantize_decimal(item.effective_quantity_mt),
                contribution_factor=quantize_decimal(item.contribution_factor),
                current_eta=ensure_utc(item.shipment.current_eta),
                current_state=item.shipment.current_state.value,
                shipment_state=item.shipment_state,
                confidence=item.confidence,
                freshness_label=item.freshness_label,
                explanation=item.explanation,
            )
            for item in shipments
        ],
        confidence_reasons=reasons,
        assumptions=assumptions,
        impact_explanation=impact_explanation,
        recommendation_why=recommendation_why_for(target.calculation),
        current_owner=current_owner_for_combo(
            db,
            context.tenant_id,
            plant_id,
            material_id,
            [item.shipment.id for item in shipments],
        ),
    )


def update_stock_risk_action(
    db: Session,
    context: RequestContext,
    plant_id: int,
    material_id: int,
    action_status: str,
) -> StockCoverDetailResponse | None:
    detail = calculate_stock_cover_detail(db, context, plant_id, material_id)
    if detail is None:
        return None
    calculation = detail.row.calculation
    if calculation.status not in {"critical", "warning"} or not calculation.recommended_action_text:
        raise ValueError("Action tracking is only available for warning or critical stock risks")

    shipments = weighted_shipments(db, context.tenant_id).get(ComboKey(plant_id, material_id), [])
    exception_case = linked_exception_for_combo(
        db,
        context.tenant_id,
        plant_id,
        material_id,
        [item.shipment.id for item in shipments],
    )
    now = datetime.now(UTC)
    if exception_case is None:
        plant = db.get(Plant, plant_id)
        material = db.get(Material, material_id)
        if plant is None or material is None:
            return None
        trigger_source = (
            "stock_cover_critical" if calculation.status == "critical" else "stock_cover_warning"
        )
        exception_case = ExceptionCase(
            tenant_id=context.tenant_id,
            type=ExceptionType.STOCKOUT_RISK,
            severity=(
                ExceptionSeverity.CRITICAL
                if calculation.status == "critical"
                else ExceptionSeverity.HIGH
            ),
            status=ExceptionStatus.OPEN,
            title=f"{plant.name} {material.name} stock cover is {calculation.status}",
            summary=(
                f"[trigger_source:{trigger_source}] Days of cover is {calculation.days_of_cover} "
                f"days for {plant.name} / {material.name}."
            ),
            linked_plant_id=plant_id,
            linked_material_id=material_id,
            triggered_at=now,
            due_at=(
                now + timedelta(hours=calculation.action_deadline_hours or 0)
                if calculation.action_deadline_hours is not None
                else None
            ),
            next_action=calculation.recommended_action_text,
            action_status="pending",
            action_started_at=None,
            action_completed_at=None,
        )
        db.add(exception_case)
        db.flush()

    exception_case.action_status = action_status
    if action_status == "pending":
        exception_case.action_started_at = None
        exception_case.action_completed_at = None
    elif action_status == "in_progress":
        exception_case.action_started_at = exception_case.action_started_at or now
        exception_case.action_completed_at = None
    elif action_status == "completed":
        exception_case.action_started_at = exception_case.action_started_at or exception_case.triggered_at
        exception_case.action_completed_at = now
    else:
        raise ValueError("Unsupported action status")

    db.commit()
    return calculate_stock_cover_detail(db, context, plant_id, material_id)


def build_stock_cover_rows(db: Session, context: RequestContext) -> list[StockCoverRow]:
    plants = {
        plant.id: plant
        for plant in db.scalars(select(Plant).where(Plant.tenant_id == context.tenant_id))
    }
    materials = {
        material.id: material
        for material in db.scalars(select(Material).where(Material.tenant_id == context.tenant_id))
    }
    thresholds = {
        ComboKey(threshold.plant_id, threshold.material_id): threshold
        for threshold in db.scalars(
            select(PlantMaterialThreshold).where(
                PlantMaterialThreshold.tenant_id == context.tenant_id
            )
        )
    }
    snapshots = latest_snapshots(db, context.tenant_id)
    shipments = weighted_shipments(db, context.tenant_id)

    combo_keys = set(snapshots) | set(thresholds) | set(shipments)
    rows: list[StockCoverRow] = []
    for combo in sorted(combo_keys, key=lambda item: (item.plant_id, item.material_id)):
        plant = plants.get(combo.plant_id)
        material = materials.get(combo.material_id)
        if plant is None or material is None:
            continue

        snapshot = snapshots.get(combo)
        threshold = thresholds.get(combo)
        combo_shipments = shipments.get(combo, [])
        rows.append(build_row(db, plant, material, snapshot, threshold, combo_shipments))

    return rows


def latest_snapshots(db: Session, tenant_id: int) -> dict[ComboKey, StockSnapshot]:
    ordered = db.scalars(
        select(StockSnapshot)
        .where(StockSnapshot.tenant_id == tenant_id)
        .order_by(
            StockSnapshot.plant_id,
            StockSnapshot.material_id,
            StockSnapshot.snapshot_time.desc(),
        )
    )
    latest: dict[ComboKey, StockSnapshot] = {}
    for snapshot in ordered:
        key = ComboKey(snapshot.plant_id, snapshot.material_id)
        latest.setdefault(key, snapshot)
    return latest


def weighted_shipments(db: Session, tenant_id: int) -> dict[ComboKey, list[WeightedShipment]]:
    grouped: dict[ComboKey, list[WeightedShipment]] = {}
    shipments = db.scalars(
        select(Shipment).where(
            Shipment.tenant_id == tenant_id,
            Shipment.current_state.in_(ACTIVE_SHIPMENT_STATES),
        )
    )
    for shipment in shipments:
        weighted = weigh_shipment(db, shipment)
        if weighted is None:
            continue
        key = ComboKey(shipment.plant_id, shipment.material_id)
        grouped.setdefault(key, []).append(weighted)
    return grouped


def weigh_shipment(db: Session, shipment: Shipment) -> WeightedShipment | None:
    item = build_shipment_item(db, shipment)
    if item.shipment_state in {"delivered", "cancelled"}:
        return None

    movement_ctx = build_movement_context(db, shipment)
    port_summary = build_port_summary(movement_ctx)
    inland_summary = build_inland_summary(movement_ctx)
    freshness_source = None
    if item.shipment_state in {"at_port", "discharging"} and port_summary:
        freshness_source = port_summary.freshness.freshness_label
    elif item.shipment_state == "in_transit" and inland_summary:
        freshness_source = inland_summary.freshness.freshness_label
    if freshness_source is None:
        freshness_source = assess_freshness(item.last_update_at).freshness_label

    state_factor = STATE_FACTORS.get(item.shipment_state, Decimal("0.25"))
    confidence_factor = CONFIDENCE_FACTORS.get(item.confidence, Decimal("0.60"))
    freshness_factor = FRESHNESS_FACTORS.get(freshness_source, Decimal("0.80"))
    contribution_factor = quantize_decimal(state_factor * confidence_factor * freshness_factor)
    effective_quantity = quantize_decimal(shipment.quantity_mt * contribution_factor)

    explanation_parts = [
        f"Base factor {state_factor} from state {item.shipment_state.replace('_', ' ')}.",
        f"Confidence factor {confidence_factor} from {item.confidence} confidence.",
        f"Freshness factor {freshness_factor} from {freshness_source} data.",
    ]
    if port_summary and item.shipment_state in {"at_port", "discharging"}:
        explanation_parts.append(
            f"Port view is {port_summary.port_status.replace('_', ' ')}."
        )
    if inland_summary and item.shipment_state == "in_transit":
        explanation_parts.append(
            f"Inland view is {inland_summary.dispatch_status.replace('_', ' ')}."
        )

    return WeightedShipment(
        shipment=shipment,
        shipment_state=item.shipment_state,
        confidence=item.confidence,
        freshness_label=freshness_source,
        raw_quantity_mt=shipment.quantity_mt,
        contribution_factor=contribution_factor,
        effective_quantity_mt=effective_quantity,
        explanation=" ".join(explanation_parts),
    )


def build_row(
    db: Session,
    plant: Plant,
    material: Material,
    snapshot: StockSnapshot | None,
    threshold: PlantMaterialThreshold | None,
    shipments: list[WeightedShipment],
) -> StockCoverRow:
    raw_inbound_pipeline_mt = sum(
        (shipment.raw_quantity_mt for shipment in shipments),
        start=Decimal("0"),
    )
    effective_inbound_pipeline_mt = sum(
        (shipment.effective_quantity_mt for shipment in shipments),
        start=Decimal("0"),
    )
    snapshot_time = snapshot.snapshot_time if snapshot else None
    freshness_hours = None
    if snapshot_time is not None:
        freshness_delta = datetime.now(UTC) - ensure_utc(snapshot_time)
        freshness_hours = quantize_decimal(
            Decimal(freshness_delta.total_seconds()) / Decimal("3600")
        )

    if snapshot is None:
        calculation = StockCoverBreakdown(
            current_stock_mt=None,
            inbound_pipeline_mt=quantize_decimal(effective_inbound_pipeline_mt),
            raw_inbound_pipeline_mt=quantize_decimal(raw_inbound_pipeline_mt),
            effective_inbound_pipeline_mt=quantize_decimal(effective_inbound_pipeline_mt),
            total_considered_mt=None,
            daily_consumption_mt=None,
            days_of_cover=None,
            threshold_days=threshold.threshold_days if threshold else None,
            warning_days=threshold.warning_days if threshold else None,
            status="insufficient_data",
            estimated_breach_date=None,
            confidence_level="low",
            insufficient_data_reason="No stock snapshot available",
            data_freshness_hours=None,
            linked_shipment_count=len(shipments),
            weighted_shipment_count=quantize_decimal(sum(
                (shipment.contribution_factor for shipment in shipments),
                start=Decimal("0"),
            )),
            risk_hours_remaining=None,
            estimated_production_exposure_mt=None,
            estimated_value_at_risk=None,
            value_per_mt_used=None,
            criticality_multiplier_used=None,
            urgency_band="monitor",
            recommended_action_code=None,
            recommended_action_text=None,
            owner_role_recommended=None,
            action_deadline_hours=None,
            action_priority=None,
            action_status=None,
            action_sla_breach=False,
            action_age_hours=None,
        )
        return stock_cover_row(plant, material, snapshot_time, calculation)

    daily_consumption = snapshot.daily_consumption_mt
    if daily_consumption <= 0:
        calculation = StockCoverBreakdown(
            current_stock_mt=quantize_decimal(snapshot.available_to_consume_mt),
            inbound_pipeline_mt=quantize_decimal(effective_inbound_pipeline_mt),
            raw_inbound_pipeline_mt=quantize_decimal(raw_inbound_pipeline_mt),
            effective_inbound_pipeline_mt=quantize_decimal(effective_inbound_pipeline_mt),
            total_considered_mt=None,
            daily_consumption_mt=quantize_decimal(daily_consumption),
            days_of_cover=None,
            threshold_days=threshold.threshold_days if threshold else None,
            warning_days=threshold.warning_days if threshold else None,
            status="insufficient_data",
            estimated_breach_date=None,
            confidence_level="low",
            insufficient_data_reason="Daily consumption is missing, zero or negative",
            data_freshness_hours=freshness_hours,
            linked_shipment_count=len(shipments),
            weighted_shipment_count=quantize_decimal(sum(
                (shipment.contribution_factor for shipment in shipments),
                start=Decimal("0"),
            )),
            risk_hours_remaining=None,
            estimated_production_exposure_mt=None,
            estimated_value_at_risk=None,
            value_per_mt_used=None,
            criticality_multiplier_used=None,
            urgency_band="monitor",
            recommended_action_code=None,
            recommended_action_text=None,
            owner_role_recommended=None,
            action_deadline_hours=None,
            action_priority=None,
            action_status=None,
            action_sla_breach=False,
            action_age_hours=None,
        )
        return stock_cover_row(plant, material, snapshot_time, calculation)

    current_stock_mt = snapshot.available_to_consume_mt
    total_considered_mt = current_stock_mt + effective_inbound_pipeline_mt
    days_of_cover = quantize_decimal(total_considered_mt / daily_consumption)
    threshold_days = threshold.threshold_days if threshold else None
    warning_days = threshold.warning_days if threshold else None
    status = risk_status(days_of_cover, threshold_days, warning_days)
    estimated_breach_date = ensure_utc(snapshot.snapshot_time) + timedelta(
        days=float(days_of_cover)
    )
    confidence_level = confidence_level_for(snapshot, threshold, shipments)
    insufficient_reason = None if threshold else "Threshold record missing for plant/material"
    protection = protection_indicator(
        quantize_decimal(raw_inbound_pipeline_mt),
        quantize_decimal(effective_inbound_pipeline_mt),
    )
    impact = calculate_impact(
        plant_code=plant.code,
        material_code=material.code,
        days_of_cover=days_of_cover,
        status=status,
        threshold_days=threshold_days,
        warning_days=warning_days,
        daily_consumption_mt=quantize_decimal(daily_consumption),
        effective_inbound_pipeline_mt=quantize_decimal(effective_inbound_pipeline_mt),
        confidence_level=confidence_level,
        elapsed_hours_since_snapshot=freshness_hours,
    )
    recommendation = recommend_action(
        status=status,
        urgency_band=impact.urgency_band,
        confidence_level=confidence_level,
        raw_inbound_pipeline_mt=quantize_decimal(raw_inbound_pipeline_mt),
        effective_inbound_pipeline_mt=quantize_decimal(effective_inbound_pipeline_mt),
        inbound_protection_indicator=protection,
        shipment_signals=[
            RecommendationSignal(
                shipment_state=item.shipment_state,
                freshness_label=item.freshness_label,
                confidence=item.confidence,
            )
            for item in shipments
        ],
    )
    action_state = resolve_action_state(
        db,
        tenant_id=plant.tenant_id,
        plant_id=plant.id,
        material_id=material.id,
        shipment_ids=[item.shipment.id for item in shipments],
        default_deadline_hours=(
            recommendation.action_deadline_hours if status in {"critical", "warning"} else None
        ),
        default_age_hours=freshness_hours,
    )

    calculation = StockCoverBreakdown(
        current_stock_mt=quantize_decimal(current_stock_mt),
        inbound_pipeline_mt=quantize_decimal(effective_inbound_pipeline_mt),
        raw_inbound_pipeline_mt=quantize_decimal(raw_inbound_pipeline_mt),
        effective_inbound_pipeline_mt=quantize_decimal(effective_inbound_pipeline_mt),
        total_considered_mt=quantize_decimal(total_considered_mt),
        daily_consumption_mt=quantize_decimal(daily_consumption),
        days_of_cover=days_of_cover,
        threshold_days=threshold_days,
        warning_days=warning_days,
        status=status,
        estimated_breach_date=estimated_breach_date,
        confidence_level=confidence_level,
        insufficient_data_reason=insufficient_reason,
        data_freshness_hours=freshness_hours,
        linked_shipment_count=len(shipments),
        weighted_shipment_count=quantize_decimal(sum(
            (shipment.contribution_factor for shipment in shipments),
            start=Decimal("0"),
        )),
        risk_hours_remaining=impact.risk_hours_remaining,
        estimated_production_exposure_mt=impact.estimated_production_exposure_mt,
        estimated_value_at_risk=impact.estimated_value_at_risk,
        value_per_mt_used=impact.value_per_mt_used,
        criticality_multiplier_used=impact.criticality_multiplier_used,
        urgency_band=impact.urgency_band,
        recommended_action_code=(
            recommendation.recommended_action_code
            if status in {"critical", "warning"}
            else None
        ),
        recommended_action_text=(
            recommendation.recommended_action_text
            if status in {"critical", "warning"}
            else None
        ),
        owner_role_recommended=(
            recommendation.owner_role_recommended
            if status in {"critical", "warning"}
            else None
        ),
        action_deadline_hours=(
            recommendation.action_deadline_hours
            if status in {"critical", "warning"}
            else None
        ),
        action_priority=(
            recommendation.action_priority
            if status in {"critical", "warning"}
            else None
        ),
        action_status=action_state.action_status if status in {"critical", "warning"} else None,
        action_sla_breach=action_state.action_sla_breach if status in {"critical", "warning"} else False,
        action_age_hours=action_state.action_age_hours if status in {"critical", "warning"} else None,
    )
    return stock_cover_row(plant, material, snapshot_time, calculation)


def stock_cover_row(
    plant: Plant,
    material: Material,
    snapshot_time: datetime | None,
    calculation: StockCoverBreakdown,
) -> StockCoverRow:
    return StockCoverRow(
        plant_id=plant.id,
        plant_code=plant.code,
        plant_name=plant.name,
        material_id=material.id,
        material_code=material.code,
        material_name=material.name,
        latest_snapshot_time=snapshot_time,
        calculation=calculation,
    )


def risk_status(
    days_of_cover: Decimal,
    threshold_days: Decimal | None,
    warning_days: Decimal | None,
) -> str:
    if threshold_days is None:
        return "warning" if days_of_cover <= Decimal("3") else "safe"
    if days_of_cover <= threshold_days:
        return "critical"
    if warning_days is not None and days_of_cover <= warning_days:
        return "warning"
    return "safe"


def confidence_level_for(
    snapshot: StockSnapshot,
    threshold: PlantMaterialThreshold | None,
    shipments: list[WeightedShipment],
) -> str:
    snapshot_age = datetime.now(UTC) - ensure_utc(snapshot.snapshot_time)
    if snapshot_age > timedelta(hours=72):
        return "low"
    if not shipments:
        return (
            "high"
            if threshold is not None and snapshot_age <= timedelta(hours=24)
            else "medium"
        )

    avg_factor = (
        sum((shipment.contribution_factor for shipment in shipments), start=Decimal("0"))
        / Decimal(len(shipments))
    )
    if (
        snapshot_age <= timedelta(hours=24)
        and threshold is not None
        and avg_factor >= Decimal("0.60")
    ):
        return "high"
    if avg_factor >= Decimal("0.35"):
        return "medium"
    return "low"


def confidence_reasons(row: StockCoverRow, shipments: list[WeightedShipment]) -> list[str]:
    reasons: list[str] = []
    if row.latest_snapshot_time is None:
        reasons.append("No stock snapshot was available.")
        return reasons

    freshness = row.calculation.data_freshness_hours
    if freshness is not None:
        if freshness <= Decimal("24"):
            reasons.append("Latest stock snapshot is recent.")
        elif freshness <= Decimal("72"):
            reasons.append("Latest stock snapshot is aging but still usable.")
        else:
            reasons.append("Latest stock snapshot is stale.")

    if row.calculation.threshold_days is None:
        reasons.append("No threshold was configured for this plant/material.")

    if shipments:
        low_confidence = [shipment for shipment in shipments if shipment.confidence == "low"]
        stale = [shipment for shipment in shipments if shipment.freshness_label == "stale"]
        if low_confidence or stale:
            reasons.append(
                "Low-confidence or stale shipment signals reduced effective inbound "
                "protection."
            )
        reasons.append(
            f"Raw inbound is {row.calculation.raw_inbound_pipeline_mt} MT, but effective "
            "inbound is "
            f"{row.calculation.effective_inbound_pipeline_mt} MT after weighting."
        )
    else:
        reasons.append("No inbound shipments contribute to the pipeline estimate.")

    if row.calculation.status == "insufficient_data" and row.calculation.insufficient_data_reason:
        reasons.append(row.calculation.insufficient_data_reason)
    return reasons


def impact_explanation_for(calculation: StockCoverBreakdown) -> list[str]:
    if calculation.estimated_production_exposure_mt is None:
        return ["Impact could not be calculated because usable cover or consumption data is missing."]
    return [
        f"Urgency band is {calculation.urgency_band.replace('_', ' ')} from the current risk horizon.",
        (
            f"Production exposure is {calculation.estimated_production_exposure_mt} MT based on "
            "daily consumption and breach severity."
        ),
        (
            f"Estimated value at risk is {calculation.estimated_value_at_risk} using "
            f"{calculation.value_per_mt_used} per MT and a multiplier of "
            f"{calculation.criticality_multiplier_used}."
        ),
        "This estimate is based on configured value per MT and a severity multiplier derived from threshold breach.",
    ]


def recommendation_why_for(calculation: StockCoverBreakdown) -> list[str]:
    if not calculation.recommended_action_text:
        return ["No action recommendation is generated for safe or insufficient-data combinations."]
    reasons = [
        f"Urgency is {calculation.urgency_band.replace('_', ' ')} with status {calculation.status.replace('_', ' ')}.",
    ]
    if calculation.confidence_level == "low":
        reasons.append("Confidence is low, so the recommendation favors immediate operational validation.")
    if calculation.effective_inbound_pipeline_mt < calculation.raw_inbound_pipeline_mt:
        reasons.append("Effective inbound protection is lower than the raw pipeline after shipment weighting.")
    return reasons


def protection_indicator(raw_inbound: Decimal, effective_inbound: Decimal) -> str:
    if raw_inbound <= 0:
        return "no_pipeline"
    ratio = effective_inbound / raw_inbound
    if ratio >= Decimal("0.75"):
        return "strong"
    if ratio >= Decimal("0.40"):
        return "reduced"
    return "weak"


def current_owner_for_combo(
    db: Session,
    tenant_id: int,
    plant_id: int,
    material_id: int,
    shipment_ids: list[int],
) -> str | None:
    action_state = resolve_action_state(
        db,
        tenant_id=tenant_id,
        plant_id=plant_id,
        material_id=material_id,
        shipment_ids=shipment_ids,
        default_deadline_hours=None,
        default_age_hours=None,
    )
    return action_state.current_owner


def resolve_action_state(
    db: Session,
    tenant_id: int,
    plant_id: int,
    material_id: int,
    shipment_ids: list[int],
    default_deadline_hours: int | None,
    default_age_hours: Decimal | None,
) -> ActionState:
    case = linked_exception_for_combo(db, tenant_id, plant_id, material_id, shipment_ids)
    if case is None:
        action_age_hours = default_age_hours
        action_sla_breach = bool(
            default_deadline_hours is not None
            and action_age_hours is not None
            and action_age_hours > Decimal(str(default_deadline_hours))
        )
        return ActionState(
            action_status="pending" if default_deadline_hours is not None else "pending",
            action_sla_breach=action_sla_breach,
            action_age_hours=action_age_hours,
            current_owner="Unassigned" if default_deadline_hours is not None else None,
            exception_id=None,
        )

    current_owner = "Unassigned"
    if case.owner_user_id is not None:
        owner = db.get(User, case.owner_user_id)
        if owner is not None:
            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.user_id == owner.id,
                    TenantMembership.is_active.is_(True),
                )
            )
            if membership:
                current_owner = owner.full_name

    action_status = case.action_status or "pending"
    started_at = case.action_started_at or case.triggered_at
    end_at = (
        case.action_completed_at
        if action_status == "completed" and case.action_completed_at
        else datetime.now(UTC)
    )
    action_age_hours = None
    if started_at is not None:
        action_age_hours = quantize_decimal(
            Decimal(str((ensure_utc(end_at) - ensure_utc(started_at)).total_seconds())) / Decimal("3600")
        )
    action_sla_breach = False
    if action_status != "completed" and case.due_at is not None:
        action_sla_breach = ensure_utc(case.due_at) < datetime.now(UTC)
    return ActionState(
        action_status=action_status,
        action_sla_breach=action_sla_breach,
        action_age_hours=action_age_hours,
        current_owner=current_owner,
        exception_id=case.id,
    )


def linked_exception_for_combo(
    db: Session,
    tenant_id: int,
    plant_id: int,
    material_id: int,
    shipment_ids: list[int],
) -> ExceptionCase | None:
    active_statuses = {
        ExceptionStatus.OPEN,
        ExceptionStatus.ACKNOWLEDGED,
        ExceptionStatus.IN_PROGRESS,
        ExceptionStatus.RESOLVED,
    }
    candidates = list(
        db.scalars(
            select(ExceptionCase)
            .where(
                ExceptionCase.tenant_id == tenant_id,
                ExceptionCase.status.in_(active_statuses),
                ExceptionCase.linked_plant_id == plant_id,
                ExceptionCase.linked_material_id == material_id,
            )
            .order_by(ExceptionCase.updated_at.desc())
        )
    )
    if shipment_ids:
        shipment_matches = list(
            db.scalars(
                select(ExceptionCase)
                .where(
                    ExceptionCase.tenant_id == tenant_id,
                    ExceptionCase.status.in_(active_statuses),
                    ExceptionCase.linked_shipment_id.in_(shipment_ids),
                )
                .order_by(ExceptionCase.updated_at.desc())
            )
        )
        candidates.extend(shipment_matches)
    deduped: list[ExceptionCase] = []
    seen: set[int] = set()
    for item in candidates:
        if item.id in seen:
            continue
        deduped.append(item)
        seen.add(item.id)
    return deduped[0] if deduped else None


def quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
