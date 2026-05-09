from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TenantScopedMixin, TimestampMixin
from app.models.enums import (
    OperationalEventCategory,
    OperationalEventFreshnessStatus,
    OperationalEventSourceType,
    OperationalEventType,
)


class OperationalEvent(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "operational_events"
    __table_args__ = (
        Index("ix_operational_events_tenant_occurred", "tenant_id", "occurred_at"),
        Index("ix_operational_events_tenant_type", "tenant_id", "event_type"),
        Index("ix_operational_events_tenant_category", "tenant_id", "event_category"),
        Index("ix_operational_events_tenant_source", "tenant_id", "source_type", "source_id"),
        Index(
            "ix_operational_events_tenant_plant_material",
            "tenant_id",
            "plant_id",
            "material_id",
        ),
        Index("ix_operational_events_tenant_shipment", "tenant_id", "shipment_id"),
        Index("ix_operational_events_tenant_supplier", "tenant_id", "supplier_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[OperationalEventType] = mapped_column(
        Enum(
            OperationalEventType,
            name="operational_event_type",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )
    event_category: Mapped[OperationalEventCategory] = mapped_column(
        Enum(
            OperationalEventCategory,
            name="operational_event_category",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )
    source_type: Mapped[OperationalEventSourceType] = mapped_column(
        Enum(
            OperationalEventSourceType,
            name="operational_event_source_type",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )
    source_id: Mapped[int | None] = mapped_column()
    source_reference: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    plant_id: Mapped[int | None] = mapped_column(ForeignKey("plants.id", ondelete="SET NULL"))
    plant_reference: Mapped[str | None] = mapped_column(String(255))
    material_id: Mapped[int | None] = mapped_column(ForeignKey("materials.id", ondelete="SET NULL"))
    material_reference: Mapped[str | None] = mapped_column(String(255))
    shipment_id: Mapped[int | None] = mapped_column(ForeignKey("shipments.id", ondelete="SET NULL"))
    shipment_reference: Mapped[str | None] = mapped_column(String(255))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
    )
    supplier_reference: Mapped[str | None] = mapped_column(String(255))
    purchase_order_reference: Mapped[str | None] = mapped_column(String(120))
    quantity_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    quantity_unit: Mapped[str | None] = mapped_column(String(20))
    previous_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    freshness_status: Mapped[OperationalEventFreshnessStatus | None] = mapped_column(
        Enum(
            OperationalEventFreshnessStatus,
            name="operational_event_freshness_status",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        )
    )
