from datetime import datetime

from pydantic import BaseModel, Field


class CarrierOption(BaseModel):
    code: str
    name: str


class CarrierDetection(BaseModel):
    owner_prefix: str
    carrier_code: str | None
    carrier_name: str | None
    confidence: str
    requires_manual_selection: bool
    options: list[CarrierOption]


class TrackingEventOut(BaseModel):
    event_type: str
    event_datetime: datetime
    location_name: str | None = None
    location_code: str | None = None
    transport_mode: str
    vessel_name: str | None = None
    voyage_no: str | None = None
    source: str
    raw_payload: dict


class ContainerSearchRequest(BaseModel):
    container_no: str = Field(min_length=1)
    carrier_code: str | None = None


class ContainerSearchResponse(BaseModel):
    container_no: str
    carrier_detection: CarrierDetection
    tracking_source: str
    events: list[TrackingEventOut]
    latest_event: TrackingEventOut | None
    latest_eta: datetime | None
    linked_statuses: list["LinkedShipmentStatus"] = Field(default_factory=list)


class LinkContainerRequest(BaseModel):
    container_no: str
    carrier_code: str
    shipment_id: int
    tracking_source: str = "mock"


class LinkedShipmentStatus(BaseModel):
    shipment_id: int
    shipment_ref: str
    container_no: str
    carrier_code: str
    tracking_source: str
    planned_eta: datetime | None
    latest_eta: datetime | None
    delay_days: int | None
    delay_status: str
    current_milestone: str | None
    current_location: str | None
    last_tracking_update_at: datetime | None
    linked_at: datetime
    already_linked: bool = False


class ShipmentOption(BaseModel):
    id: int
    shipment_id: str
    plant_name: str
    material_name: str
    planned_eta: datetime
    current_eta: datetime
