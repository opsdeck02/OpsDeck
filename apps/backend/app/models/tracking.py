from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TenantScopedMixin, TimestampMixin


class TrackingSource(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "tracking_sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_tracking_sources_tenant_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(40), nullable=False, default="mock")
    is_active: Mapped[bool] = mapped_column(default=True)


class Container(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "containers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "container_no", name="uq_containers_tenant_container_no"),
        Index("ix_containers_tenant_carrier", "tenant_id", "carrier_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    container_no: Mapped[str] = mapped_column(String(11), nullable=False)
    carrier_code: Mapped[str | None] = mapped_column(String(40))
    tracking_source: Mapped[str | None] = mapped_column(String(40))
    detection_confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")


class ShipmentContainer(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "shipment_containers"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "shipment_id",
            "container_id",
            name="uq_shipment_containers_tenant_link",
        ),
        Index("ix_shipment_containers_tenant_container", "tenant_id", "container_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"))
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id", ondelete="CASCADE"))
    carrier_code: Mapped[str] = mapped_column(String(40), nullable=False)
    tracking_source: Mapped[str] = mapped_column(String(40), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrackingEvent(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "tracking_events"
    __table_args__ = (
        Index(
            "ix_tracking_events_tenant_container_time",
            "tenant_id",
            "container_id",
            "event_datetime",
        ),
        Index(
            "ix_tracking_events_tenant_shipment_time",
            "tenant_id",
            "shipment_id",
            "event_datetime",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id", ondelete="CASCADE"))
    shipment_id: Mapped[int | None] = mapped_column(ForeignKey("shipments.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    event_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location_name: Mapped[str | None] = mapped_column(String(255))
    location_code: Mapped[str | None] = mapped_column(String(40))
    transport_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    vessel_name: Mapped[str | None] = mapped_column(String(255))
    voyage_no: Mapped[str | None] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_payload: Mapped[str | None] = mapped_column(String)
