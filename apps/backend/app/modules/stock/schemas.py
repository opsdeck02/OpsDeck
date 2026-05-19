from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.modules.impact.schemas import OperationalInterruptionImpact


class StockCoverBreakdown(BaseModel):
    current_stock_mt: Decimal | None
    inbound_pipeline_mt: Decimal
    raw_inbound_pipeline_mt: Decimal
    effective_inbound_pipeline_mt: Decimal
    total_considered_mt: Decimal | None
    daily_consumption_mt: Decimal | None
    days_of_cover: Decimal | None
    threshold_days: Decimal | None
    warning_days: Decimal | None
    status: str
    estimated_breach_date: datetime | None
    confidence_level: str
    insufficient_data_reason: str | None
    data_freshness_hours: Decimal | None
    linked_shipment_count: int
    weighted_shipment_count: Decimal
    risk_hours_remaining: Decimal | None
    estimated_production_exposure_mt: Decimal | None
    estimated_value_at_risk: Decimal | None
    operational_interruption_impact: OperationalInterruptionImpact | None = None
    value_per_mt_used: Decimal | None
    criticality_multiplier_used: Decimal | None
    urgency_band: str
    recommended_action_code: str | None
    recommended_action_text: str | None
    owner_role_recommended: str | None
    action_deadline_hours: int | None
    action_priority: str | None
    action_status: str | None
    action_sla_breach: bool
    action_age_hours: Decimal | None


class StockCoverRow(BaseModel):
    plant_id: int
    plant_code: str
    plant_name: str
    material_id: int
    material_code: str
    material_name: str
    latest_snapshot_time: datetime | None
    calculation: StockCoverBreakdown


class StockCoverSummaryResponse(BaseModel):
    total_combinations: int
    critical_risks: int
    warnings: int
    insufficient_data: int
    rows: list[StockCoverRow]


class ShipmentContribution(BaseModel):
    id: int
    shipment_id: str
    supplier_name: str
    raw_quantity_mt: Decimal
    effective_quantity_mt: Decimal
    contribution_factor: Decimal
    current_eta: datetime
    current_state: str
    shipment_state: str
    confidence: str
    freshness_label: str
    explanation: str


class StockCoverDetailResponse(BaseModel):
    row: StockCoverRow
    shipments: list[ShipmentContribution]
    confidence_reasons: list[str]
    assumptions: list[str]
    impact_explanation: list[str]
    recommendation_why: list[str]
    current_owner: str | None


class StockRiskActionRequest(BaseModel):
    action_status: str


class InventoryContinuityResult(BaseModel):
    plant_reference: str
    material_reference: str
    on_hand_quantity: Decimal
    reserved_quantity: Decimal
    blocked_quantity: Decimal
    quality_hold_quantity: Decimal
    usable_quantity: Decimal
    inbound_committed_quantity: Decimal
    inbound_uncertain_quantity: Decimal
    daily_consumption_rate: Decimal | None
    days_of_cover: Decimal | None
    raw_days_of_cover: Decimal | None = None
    threshold_days: Decimal | None = None
    warning_days: Decimal | None = None
    minimum_buffer_stock_days: Decimal | None = None
    minimum_buffer_stock_mt: Decimal | None = None
    stockout_alert_horizon_days: Decimal | None = None
    trusted_inbound_quantity: Decimal = Decimal("0")
    uncertain_inbound_quantity: Decimal = Decimal("0")
    trusted_days_of_cover: Decimal | None = None
    projected_exhaustion_date: datetime | None
    cover_confidence_score: Decimal | None = None
    freshness_status: str = "unknown"
    trust_warnings: list[str] = []
    unit: str
    calculation_reasons: list[str]
