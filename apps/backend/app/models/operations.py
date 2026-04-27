from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TenantScopedMixin, TimestampMixin
from app.models.enums import ExceptionSeverity, ExceptionStatus, ExceptionType


class StockSnapshot(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "stock_snapshots"
    __table_args__ = (
        Index(
            "ix_stock_snapshots_tenant_plant_material_time",
            "tenant_id",
            "plant_id",
            "material_id",
            "snapshot_time",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id", ondelete="CASCADE"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"))
    on_hand_mt: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quality_held_mt: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    available_to_consume_mt: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    daily_consumption_mt: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PortEvent(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "port_events"
    __table_args__ = (
        Index("ix_port_events_tenant_shipment", "tenant_id", "shipment_id"),
        Index("ix_port_events_tenant_status", "tenant_id", "berth_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"))
    berth_status: Mapped[str] = mapped_column(String(80), nullable=False)
    waiting_days: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    discharge_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discharge_rate_mt_per_day: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    estimated_demurrage_exposure: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))


class InlandMovement(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "inland_movements"
    __table_args__ = (
        Index("ix_inland_movements_tenant_shipment", "tenant_id", "shipment_id"),
        Index("ix_inland_movements_tenant_state", "tenant_id", "current_state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(String(40), nullable=False)
    carrier_name: Mapped[str | None] = mapped_column(String(255))
    origin_location: Mapped[str | None] = mapped_column(String(255))
    destination_location: Mapped[str | None] = mapped_column(String(255))
    planned_departure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_arrival_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_departure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_arrival_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_state: Mapped[str] = mapped_column(String(80), nullable=False)


class ExceptionCase(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "exception_cases"
    __table_args__ = (
        Index("ix_exception_cases_tenant_status_severity", "tenant_id", "status", "severity"),
        Index("ix_exception_cases_tenant_due_at", "tenant_id", "due_at"),
        Index("ix_exception_cases_tenant_owner", "tenant_id", "owner_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[ExceptionType] = mapped_column(
        Enum(
            ExceptionType,
            name="exception_type",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )
    severity: Mapped[ExceptionSeverity] = mapped_column(
        Enum(
            ExceptionSeverity,
            name="exception_severity",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[ExceptionStatus] = mapped_column(
        Enum(
            ExceptionStatus,
            name="exception_status",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
        default=ExceptionStatus.OPEN,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(String)
    linked_shipment_id: Mapped[int | None] = mapped_column(
        ForeignKey("shipments.id", ondelete="SET NULL")
    )
    linked_plant_id: Mapped[int | None] = mapped_column(
        ForeignKey("plants.id", ondelete="SET NULL")
    )
    linked_material_id: Mapped[int | None] = mapped_column(
        ForeignKey("materials.id", ondelete="SET NULL")
    )
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_action: Mapped[str | None] = mapped_column(String)
    action_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    action_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    action_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExceptionComment(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "exception_comments"
    __table_args__ = (Index("ix_exception_comments_tenant_case", "tenant_id", "exception_case_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    exception_case_id: Mapped[int] = mapped_column(
        ForeignKey("exception_cases.id", ondelete="CASCADE")
    )
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    comment: Mapped[str] = mapped_column(String, nullable=False)


class AuditLog(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_entity", "tenant_id", "entity_type", "entity_id"),
        Index("ix_audit_logs_tenant_actor", "tenant_id", "actor_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(String)


class LineStopIncident(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "line_stop_incidents"
    __table_args__ = (
        Index("ix_line_stop_incidents_tenant_stopped_at", "tenant_id", "stopped_at"),
        Index(
            "ix_line_stop_incidents_tenant_plant_material",
            "tenant_id",
            "plant_id",
            "material_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id", ondelete="RESTRICT"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="RESTRICT"))
    stopped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(String)
