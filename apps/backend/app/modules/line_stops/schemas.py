from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class LineStopIncidentCreate(BaseModel):
    plant_id: int
    material_id: int
    stopped_at: datetime
    duration_hours: Decimal = Field(gt=0)
    notes: str | None = None


class LineStopIncidentOut(BaseModel):
    id: int
    plant_id: int
    plant_name: str
    material_id: int
    material_name: str
    stopped_at: datetime
    duration_hours: Decimal
    notes: str | None
    created_at: datetime


class LineStopIncidentListResponse(BaseModel):
    total_incidents: int
    total_duration_hours: Decimal
    items: list[LineStopIncidentOut]


class HistoricalValidationIncidentResult(BaseModel):
    incident_id: int
    plant_id: int
    plant_name: str
    plant_reference: str | None = None
    material_id: int
    material_name: str
    material_reference: str | None = None
    incident_date: datetime
    incident_type: str = "LINE_STOP"
    line_stop_duration_hours: Decimal | None = None
    business_impact: str | None = None
    opsdeck_detection_result: str | None = None
    incident_start_date: datetime | None = None
    earliest_detection_date: datetime | None = None
    warning_lead_time_hours: Decimal | None = None
    warning_lead_time_days: Decimal | None = None
    predicted_warning_date: datetime | None
    lead_time_gained_hours: Decimal | None
    status_explanation: str | None = None
    replay_caveat: str | None = None
    stock_snapshot_time_used: datetime | None = None
    available_stock_at_snapshot: Decimal | None = None
    daily_consumption_used: Decimal | None = None
    threshold_days_used: Decimal | None = None
    warning_days_used: Decimal | None = None
    inbound_quantity_due_before_incident: Decimal = Decimal("0")
    first_inbound_eta: datetime | None = None
    missing_data_limitations: list[str] = []
    detection_signals: list[str] = []
    detection_chain: list[str] = []
    recommended_actions_replay: list[str] = []
    missed_signals: list[str]
    missed_incident_analysis: list[str] = []
    confidence_level: str
    confidence_classification: str | None = None
    confidence_rationale: list[str] = []
    calibration_status: str


class HistoricalValidationSummary(BaseModel):
    incidents_analyzed: int
    detected: int
    partially_detected: int
    missed: int
    detection_rate_percent: Decimal
    average_warning_lead_time_days: Decimal | None
    longest_warning_lead_time_days: Decimal | None
    shortest_warning_lead_time_days: Decimal | None


class HistoricalValidationReport(BaseModel):
    total_incidents: int
    incidents_with_warning: int
    incidents_missed: int
    average_lead_time_hours: Decimal | None
    summary: HistoricalValidationSummary | None = None
    results: list[HistoricalValidationIncidentResult]
    generated_at: datetime | None = None
    tenant: str | None = None
    report_markdown: str | None = None
