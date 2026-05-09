from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class ContinuityRiskSnapshotCreate(BaseModel):
    tenant_id: int
    risk_fingerprint: str
    risk_type: str
    severity: str
    plant_reference: str | None = None
    material_reference: str | None = None
    shipment_reference: str | None = None
    supplier_reference: str | None = None
    snapshot_time: datetime
    days_of_cover: Decimal | None = None
    projected_exhaustion_date: datetime | None = None
    exposure_level: str | None = None
    exposure_basis: str | None = None
    exposure_value: Decimal | None = None
    shipment_delay_hours: Decimal | None = None
    tracking_freshness_minutes: Decimal | None = None
    freshness_status: str | None = None
    confidence_score: Decimal | None = None
    usable_stock: Decimal | None = None
    blocked_stock: Decimal | None = None
    incoming_quantity: Decimal | None = None
    escalation_state: str | None = None
    escalation_score: Decimal | None = None
    escalation_reason: str | None = None
    source_event_ids: list[int] | None = None
    metadata: dict[str, Any] | None = None


class ContinuityRiskSnapshotRead(ContinuityRiskSnapshotCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class RiskEscalationComparison(BaseModel):
    escalation_state: str
    escalation_score: Decimal
    escalation_reason: str
    prior_days_of_cover: Decimal | None = None
    current_days_of_cover: Decimal | None = None
    days_of_cover_delta: Decimal | None = None
    prior_shipment_delay_hours: Decimal | None = None
    current_shipment_delay_hours: Decimal | None = None
    shipment_delay_delta_hours: Decimal | None = None
    prior_severity: str | None = None
    current_severity: str | None = None
    prior_exposure_level: str | None = None
    current_exposure_level: str | None = None
