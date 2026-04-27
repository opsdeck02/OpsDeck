from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.modules.shipments.schemas import ShipmentListItem


class SupplierBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=40)
    primary_port: str | None = None
    secondary_ports: list[str] | None = None
    material_categories: list[str] | None = None
    country_of_origin: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    is_active: bool = True


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=40)
    primary_port: str | None = None
    secondary_ports: list[str] | None = None
    material_categories: list[str] | None = None
    country_of_origin: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    is_active: bool | None = None


class SupplierPerformance(BaseModel):
    total_shipments: int
    active_shipments: int
    on_time_reliability_pct: Decimal
    avg_eta_drift_hours: Decimal
    risk_signal_pct: Decimal
    total_value_at_risk: Decimal
    materials_supplied: list[str]
    ports_used: list[str]
    last_shipment_date: datetime | None
    reliability_grade: str


class SupplierOut(SupplierBase):
    id: uuid.UUID
    tenant_id: int
    created_at: datetime
    updated_at: datetime
    performance: SupplierPerformance


class SupplierDetail(SupplierOut):
    linked_shipments: list[ShipmentListItem]


class SupplierLinkShipmentsResponse(BaseModel):
    supplier_id: uuid.UUID
    matched_supplier_name: str
    linked_shipments: int


class SupplierPerformanceSummary(BaseModel):
    top_suppliers: list[SupplierOut]
    bottom_suppliers: list[SupplierOut]
    grade_d_count: int
    high_risk_supplier_count: int
