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
    material_id: int
    material_name: str
    incident_date: datetime
    predicted_warning_date: datetime | None
    lead_time_gained_hours: Decimal | None
    missed_signals: list[str]
    confidence_level: str
    calibration_status: str


class HistoricalValidationReport(BaseModel):
    total_incidents: int
    incidents_with_warning: int
    incidents_missed: int
    average_lead_time_hours: Decimal | None
    results: list[HistoricalValidationIncidentResult]
