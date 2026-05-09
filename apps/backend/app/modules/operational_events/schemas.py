from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    OperationalEventCategory,
    OperationalEventFreshnessStatus,
    OperationalEventSourceType,
    OperationalEventType,
)


class OperationalEventCreate(BaseModel):
    tenant_id: int
    event_type: OperationalEventType
    event_category: OperationalEventCategory
    source_type: OperationalEventSourceType
    source_id: int | None = None
    source_reference: str | None = None
    occurred_at: datetime | None = None
    detected_at: datetime | None = None
    plant_id: int | None = None
    plant_reference: str | None = None
    material_id: int | None = None
    material_reference: str | None = None
    shipment_id: int | None = None
    shipment_reference: str | None = None
    supplier_id: uuid.UUID | None = None
    supplier_reference: str | None = None
    purchase_order_reference: str | None = None
    quantity_value: Decimal | None = None
    quantity_unit: str | None = None
    previous_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = Field(default=None)
    confidence_score: Decimal | None = None
    freshness_status: OperationalEventFreshnessStatus | None = None


class OperationalEventOut(OperationalEventCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias="metadata_json",
        serialization_alias="metadata",
    )
    detected_at: datetime
    created_at: datetime
    updated_at: datetime
