from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ShipmentListItem(BaseModel):
    id: int
    shipment_id: str
    plant_id: int
    plant_name: str
    material_id: int
    material_name: str
    supplier_name: str
    quantity_mt: Decimal
    vessel_name: str | None
    origin_port: str | None
    destination_port: str | None
    planned_eta: datetime
    current_eta: datetime
    latest_eta: datetime | None = None
    delay_days: int | None = None
    delay_status: str = "unknown"
    current_milestone: str | None = None
    current_location: str | None = None
    last_tracking_update_at: datetime | None = None
    shipment_state: str
    confidence: str
    latest_status_source: str
    last_update_at: datetime
    contributing_data_sources: list[str]
    contribution_band: str


class ShipmentUpdateEvent(BaseModel):
    source: str
    event_type: str
    event_time: datetime
    notes: str | None


class PortEventOut(BaseModel):
    berth_status: str
    waiting_days: Decimal
    discharge_started_at: datetime | None
    discharge_rate_mt_per_day: Decimal | None
    estimated_demurrage_exposure: Decimal | None
    updated_at: datetime


class InlandMovementOut(BaseModel):
    mode: str
    carrier_name: str | None
    origin_location: str | None
    destination_location: str | None
    planned_departure_at: datetime | None
    planned_arrival_at: datetime | None
    actual_departure_at: datetime | None
    actual_arrival_at: datetime | None
    current_state: str
    updated_at: datetime


class FreshnessInfo(BaseModel):
    last_updated_at: datetime | None
    freshness_hours: Decimal | None
    freshness_label: str


class PortMonitoringItem(BaseModel):
    shipment_id: str
    plant_id: int
    plant_name: str
    material_id: int
    material_name: str
    port_status: str
    latest_berth_state: str
    waiting_time_days: Decimal
    latest_discharge_timestamp: datetime | None
    likely_port_delay: bool
    stale_record: bool
    missing_supporting_signal: bool
    freshness: FreshnessInfo
    confidence: str
    confidence_reasons: list[str]


class InlandMonitoringItem(BaseModel):
    shipment_id: str
    plant_id: int
    plant_name: str
    material_id: int
    material_name: str
    dispatch_status: str
    transporter_name: str | None
    expected_arrival: datetime | None
    actual_arrival: datetime | None
    inland_delay_flag: bool
    stale_record: bool
    missing_supporting_signal: bool
    freshness: FreshnessInfo
    confidence: str
    confidence_reasons: list[str]


class MovementDetailResponse(BaseModel):
    shipment: ShipmentListItem
    port_summary: PortMonitoringItem | None
    inland_summary: InlandMonitoringItem | None
    overall_confidence: str
    overall_freshness: FreshnessInfo
    missing_signals: list[str]
    progress_notes: list[str]


class ShipmentDetailResponse(BaseModel):
    shipment: ShipmentListItem
    supplier_name: str
    imo_number: str | None
    mmsi: str | None
    eta_confidence: Decimal | None
    source_of_truth: str
    confidence_reasons: list[str]
    fallback_notes: list[str]
    updates: list[ShipmentUpdateEvent]
    port_events: list[PortEventOut]
    inland_movements: list[InlandMovementOut]
    port_summary: PortMonitoringItem | None
    inland_summary: InlandMonitoringItem | None
    movement_gaps: list[str]
    movement_notes: list[str]


class ShipmentContinuityResult(BaseModel):
    shipment_reference: str
    status: str
    eta: datetime | None
    previous_eta: datetime | None
    eta_slip_days: Decimal | None
    current_milestone: str | None
    missing_milestones: list[str]
    overdue_milestones: list[str]
    tracking_freshness_status: str
    linked_purchase_order_reference: str | None
    linked_material_reference: str | None
    linked_plant_reference: str | None
    continuity_reasons: list[str]
