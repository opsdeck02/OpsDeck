from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Material, PortEvent, Shipment, Supplier
from app.models.enums import ShipmentState
from app.modules.shipments.confidence import assess_freshness, ensure_utc
from app.modules.shipments.movement import build_context, build_inland_summary, build_port_summary
from app.modules.shipments.service import build_shipment_item
from app.modules.stock.service import calculate_stock_cover_summary
from app.modules.suppliers.schemas import (
    SupplierCreate,
    SupplierDetail,
    SupplierLinkShipmentsResponse,
    SupplierOut,
    SupplierPerformance,
    SupplierPerformanceSummary,
    SupplierUpdate,
)
from app.schemas.context import RequestContext

ACTIVE_STATES = {
    ShipmentState.PLANNED,
    ShipmentState.IN_TRANSIT,
    ShipmentState.AT_PORT,
    ShipmentState.DISCHARGING,
    ShipmentState.INLAND_TRANSIT,
    ShipmentState.DELAYED,
}

GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}


def list_suppliers(db: Session, context: RequestContext) -> list[SupplierOut]:
    suppliers = list(
        db.scalars(
            select(Supplier)
            .where(Supplier.tenant_id == context.tenant_id)
            .order_by(Supplier.is_active.desc(), Supplier.name.asc())
        )
    )
    return [serialize_supplier(db, context, supplier) for supplier in suppliers]


def get_supplier_detail(
    db: Session,
    context: RequestContext,
    supplier_id: uuid.UUID,
) -> SupplierDetail | None:
    supplier = supplier_for_tenant(db, context.tenant_id, supplier_id)
    if supplier is None:
        return None
    base = serialize_supplier(db, context, supplier)
    shipments = linked_shipments(db, context.tenant_id, supplier.id)
    return SupplierDetail(
        **base.model_dump(),
        linked_shipments=[build_shipment_item(db, shipment) for shipment in shipments],
    )


def create_supplier(db: Session, context: RequestContext, payload: SupplierCreate) -> SupplierOut:
    supplier = Supplier(
        tenant_id=context.tenant_id,
        name=payload.name.strip(),
        code=payload.code.strip().upper(),
        primary_port=clean_optional(payload.primary_port),
        secondary_ports=clean_list(payload.secondary_ports),
        material_categories=clean_list(payload.material_categories),
        country_of_origin=clean_optional(payload.country_of_origin),
        contact_name=clean_optional(payload.contact_name),
        contact_email=str(payload.contact_email).lower() if payload.contact_email else None,
        is_active=payload.is_active,
    )
    db.add(supplier)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise ValueError("Supplier name or code already exists for this tenant")
    db.refresh(supplier)
    return serialize_supplier(db, context, supplier)


def update_supplier(
    db: Session,
    context: RequestContext,
    supplier_id: uuid.UUID,
    payload: SupplierUpdate,
) -> SupplierOut | None:
    supplier = supplier_for_tenant(db, context.tenant_id, supplier_id)
    if supplier is None:
        return None

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field == "code" and value is not None:
            value = value.strip().upper()
        elif field in {"name", "primary_port", "country_of_origin", "contact_name"}:
            value = clean_optional(value)
        elif field == "contact_email":
            value = str(value).lower() if value else None
        elif field in {"secondary_ports", "material_categories"}:
            value = clean_list(value)
        setattr(supplier, field, value)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise ValueError("Supplier name or code already exists for this tenant")
    db.refresh(supplier)
    return serialize_supplier(db, context, supplier)


def soft_delete_supplier(
    db: Session,
    context: RequestContext,
    supplier_id: uuid.UUID,
) -> SupplierOut | None:
    supplier = supplier_for_tenant(db, context.tenant_id, supplier_id)
    if supplier is None:
        return None
    supplier.is_active = False
    db.commit()
    db.refresh(supplier)
    return serialize_supplier(db, context, supplier)


def link_shipments_by_supplier_name(
    db: Session,
    context: RequestContext,
    supplier_id: uuid.UUID,
) -> SupplierLinkShipmentsResponse | None:
    supplier = supplier_for_tenant(db, context.tenant_id, supplier_id)
    if supplier is None:
        return None
    linked = list(
        db.scalars(
            select(Shipment).where(
                Shipment.tenant_id == context.tenant_id,
                func.lower(Shipment.supplier_name) == supplier.name.lower(),
            )
        )
    )
    for shipment in linked:
        shipment.supplier_id = supplier.id
    db.commit()
    return SupplierLinkShipmentsResponse(
        supplier_id=supplier.id,
        matched_supplier_name=supplier.name,
        linked_shipments=len(linked),
    )


def performance_summary(db: Session, context: RequestContext) -> SupplierPerformanceSummary:
    suppliers = list_suppliers(db, context)
    active = [supplier for supplier in suppliers if supplier.is_active]
    top = sorted(
        active,
        key=lambda item: (
            GRADE_ORDER[item.performance.reliability_grade],
            -item.performance.on_time_reliability_pct,
            item.name.lower(),
        ),
    )[:5]
    bottom = sorted(
        active,
        key=lambda item: (
            -GRADE_ORDER[item.performance.reliability_grade],
            item.performance.on_time_reliability_pct,
            item.name.lower(),
        ),
    )[:5]
    return SupplierPerformanceSummary(
        top_suppliers=top,
        bottom_suppliers=bottom,
        grade_d_count=sum(1 for item in active if item.performance.reliability_grade == "D"),
        high_risk_supplier_count=sum(
            1 for item in active if item.performance.risk_signal_pct > Decimal("50")
        ),
    )


def serialize_supplier(db: Session, context: RequestContext, supplier: Supplier) -> SupplierOut:
    return SupplierOut(
        id=supplier.id,
        tenant_id=supplier.tenant_id,
        name=supplier.name,
        code=supplier.code,
        primary_port=supplier.primary_port,
        secondary_ports=supplier.secondary_ports,
        material_categories=supplier.material_categories,
        country_of_origin=supplier.country_of_origin,
        contact_name=supplier.contact_name,
        contact_email=supplier.contact_email,
        is_active=supplier.is_active,
        created_at=ensure_utc(supplier.created_at),
        updated_at=ensure_utc(supplier.updated_at),
        performance=calculate_supplier_performance(db, context, supplier),
    )


def calculate_supplier_performance(
    db: Session,
    context: RequestContext,
    supplier: Supplier,
) -> SupplierPerformance:
    shipments = linked_shipments(db, context.tenant_id, supplier.id)
    active_shipments = [item for item in shipments if item.current_state in ACTIVE_STATES]
    eta_drifts = [
        Decimal(str((ensure_utc(item.current_eta) - ensure_utc(item.planned_eta)).total_seconds()))
        / Decimal("3600")
        for item in shipments
    ]
    on_time = sum(1 for drift in eta_drifts if abs(drift) <= Decimal("24"))
    risk_shipments = sum(1 for item in active_shipments if shipment_has_risk_signal(db, item))
    materials = material_names_for_shipments(db, shipments)
    ports = sorted(
        {
            port
            for shipment in shipments
            for port in (shipment.origin_port, shipment.destination_port)
            if port
        }
    )
    last_shipment_date = max(
        (ensure_utc(item.current_eta) for item in shipments),
        default=None,
    )
    total_value_at_risk = supplier_value_at_risk(db, context, shipments)
    reliability_pct = percentage(on_time, len(shipments))
    return SupplierPerformance(
        total_shipments=len(shipments),
        active_shipments=len(active_shipments),
        on_time_reliability_pct=reliability_pct,
        avg_eta_drift_hours=quantize_decimal(
            sum(eta_drifts, start=Decimal("0")) / Decimal(len(eta_drifts))
            if eta_drifts
            else Decimal("0")
        ),
        risk_signal_pct=percentage(risk_shipments, len(active_shipments)),
        total_value_at_risk=total_value_at_risk,
        materials_supplied=materials,
        ports_used=ports,
        last_shipment_date=last_shipment_date,
        reliability_grade=reliability_grade(reliability_pct),
    )


def supplier_value_at_risk(
    db: Session,
    context: RequestContext,
    shipments: list[Shipment],
) -> Decimal:
    combos = {(item.plant_id, item.material_id) for item in shipments}
    if not combos:
        return Decimal("0.00")
    summary = calculate_stock_cover_summary(db, context)
    total = Decimal("0")
    seen: set[tuple[int, int]] = set()
    for row in summary.rows:
        key = (row.plant_id, row.material_id)
        if key not in combos or key in seen or row.calculation.status != "critical":
            continue
        total += row.calculation.estimated_value_at_risk or Decimal("0")
        seen.add(key)
    return quantize_decimal(total)


def shipment_has_risk_signal(db: Session, shipment: Shipment) -> bool:
    item = build_shipment_item(db, shipment)
    movement_ctx = build_context(db, shipment)
    port_summary = build_port_summary(movement_ctx)
    inland_summary = build_inland_summary(movement_ctx)
    return any(
        [
            item.confidence == "low",
            assess_freshness(item.last_update_at).freshness_label == "stale",
            bool(port_summary and (port_summary.stale_record or port_summary.likely_port_delay)),
            bool(inland_summary and (inland_summary.stale_record or inland_summary.inland_delay_flag)),
        ]
    )


def linked_shipments(db: Session, tenant_id: int, supplier_id: uuid.UUID) -> list[Shipment]:
    return list(
        db.scalars(
            select(Shipment)
            .where(Shipment.tenant_id == tenant_id, Shipment.supplier_id == supplier_id)
            .order_by(Shipment.current_eta.desc())
        )
    )


def material_names_for_shipments(db: Session, shipments: list[Shipment]) -> list[str]:
    material_ids = sorted({item.material_id for item in shipments})
    if not material_ids:
        return []
    materials = list(db.scalars(select(Material).where(Material.id.in_(material_ids))))
    return sorted({item.name for item in materials})


def supplier_for_tenant(
    db: Session,
    tenant_id: int,
    supplier_id: uuid.UUID,
) -> Supplier | None:
    return db.scalar(
        select(Supplier).where(Supplier.id == supplier_id, Supplier.tenant_id == tenant_id)
    )


def find_supplier_by_name(db: Session, tenant_id: int, supplier_name: str) -> Supplier | None:
    return db.scalar(
        select(Supplier).where(
            Supplier.tenant_id == tenant_id,
            Supplier.is_active.is_(True),
            func.lower(Supplier.name) == supplier_name.strip().lower(),
        )
    )


def reliability_grade(on_time_reliability_pct: Decimal) -> str:
    if on_time_reliability_pct >= Decimal("85"):
        return "A"
    if on_time_reliability_pct >= Decimal("70"):
        return "B"
    if on_time_reliability_pct >= Decimal("50"):
        return "C"
    return "D"


def percentage(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.00")
    return quantize_decimal((Decimal(numerator) / Decimal(denominator)) * Decimal("100"))


def quantize_decimal(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def clean_list(values: list[str] | None) -> list[str] | None:
    cleaned = [value.strip() for value in (values or []) if value.strip()]
    return cleaned or None
