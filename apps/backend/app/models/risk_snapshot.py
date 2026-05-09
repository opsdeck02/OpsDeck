from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TenantScopedMixin, TimestampMixin


class ContinuityRiskSnapshot(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "continuity_risk_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "risk_fingerprint",
            "snapshot_time",
            name="uq_continuity_risk_snapshots_tenant_fingerprint_time",
        ),
        Index(
            "ix_continuity_risk_snapshots_tenant_fingerprint_time",
            "tenant_id",
            "risk_fingerprint",
            "snapshot_time",
        ),
        Index(
            "ix_continuity_risk_snapshots_tenant_context",
            "tenant_id",
            "plant_reference",
            "material_reference",
            "shipment_reference",
        ),
        Index(
            "ix_continuity_risk_snapshots_tenant_type_severity",
            "tenant_id",
            "risk_type",
            "severity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    risk_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    risk_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    plant_reference: Mapped[str | None] = mapped_column(String(255))
    material_reference: Mapped[str | None] = mapped_column(String(255))
    shipment_reference: Mapped[str | None] = mapped_column(String(255))
    supplier_reference: Mapped[str | None] = mapped_column(String(255))
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    days_of_cover: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    projected_exhaustion_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exposure_level: Mapped[str | None] = mapped_column(String(40))
    exposure_basis: Mapped[str | None] = mapped_column(String(80))
    exposure_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    shipment_delay_hours: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    tracking_freshness_minutes: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    freshness_status: Mapped[str | None] = mapped_column(String(40))
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    usable_stock: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    blocked_stock: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    incoming_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    escalation_state: Mapped[str | None] = mapped_column(String(40))
    escalation_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    escalation_reason: Mapped[str | None] = mapped_column(Text)
    source_event_ids: Mapped[list[int] | None] = mapped_column(JSON)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
