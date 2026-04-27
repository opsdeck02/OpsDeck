from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


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
