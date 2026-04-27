from datetime import datetime
from decimal import Decimal

import uuid

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TenantScopedMixin, TimestampMixin
from app.models.enums import ShipmentState


class Shipment(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "shipment_id", name="uq_shipments_tenant_business_key"),
        Index("ix_shipments_tenant_plant_state", "tenant_id", "plant_id", "current_state"),
        Index("ix_shipments_tenant_material_eta", "tenant_id", "material_id", "current_eta"),
        Index("ix_shipments_tenant_latest_update", "tenant_id", "latest_update_at"),
        Index("ix_shipments_imo_number", "imo_number"),
        Index("ix_shipments_mmsi", "mmsi"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[str] = mapped_column(String(80), nullable=False)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="RESTRICT"))
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id", ondelete="RESTRICT"))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
    )
    supplier_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity_mt: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    vessel_name: Mapped[str | None] = mapped_column(String(255))
    imo_number: Mapped[str | None] = mapped_column(String(20))
    mmsi: Mapped[str | None] = mapped_column(String(20))
    origin_port: Mapped[str | None] = mapped_column(String(255))
    destination_port: Mapped[str | None] = mapped_column(String(255))
    planned_eta: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_eta: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    eta_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    current_state: Mapped[ShipmentState] = mapped_column(
        Enum(
            ShipmentState,
            name="shipment_state",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
        default=ShipmentState.PLANNED,
    )
    source_of_truth: Mapped[str] = mapped_column(String(80), nullable=False)
    latest_update_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ShipmentUpdate(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "shipment_updates"
    __table_args__ = (
        Index("ix_shipment_updates_tenant_shipment_time", "tenant_id", "shipment_id", "event_time"),
        Index("ix_shipment_updates_tenant_source", "tenant_id", "source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(String)
