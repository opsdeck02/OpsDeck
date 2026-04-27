from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import ShipmentState


class ShipmentOut(BaseModel):
    id: int
    shipment_id: str
    material_id: int
    plant_id: int
    supplier_name: str
    quantity_mt: Decimal
    vessel_name: str | None
    imo_number: str | None
    mmsi: str | None
    origin_port: str | None
    destination_port: str | None
    planned_eta: datetime
    current_eta: datetime
    eta_confidence: Decimal | None
    current_state: ShipmentState
    source_of_truth: str
    latest_update_at: datetime
