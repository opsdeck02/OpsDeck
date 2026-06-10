from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VISIBILITY_PROFILES = {"ocean", "port", "inland", "rail", "mixed", "unknown"}


class ProductionInterruptionImpactConfigPayload(BaseModel):
    plant_id: int
    material_id: int
    production_line_id: int | None = None
    production_rate_mt_per_hour: Decimal = Field(ge=0)
    finished_goods_value_per_mt: Decimal = Field(ge=0)
    survivable_hours_without_material: Decimal = Field(ge=0)
    line_dependency_ratio: Decimal = Field(ge=0, le=1)
    downtime_cost_per_hour: Decimal = Field(ge=0)
    restart_cost: Decimal = Field(ge=0)
    restart_time_hours: Decimal = Field(ge=0)
    substitution_factor: Decimal = Field(ge=0, le=1)
    cascading_impact_factor: Decimal = Field(ge=0)
    interruption_probability_override: Decimal | None = Field(default=None, ge=0, le=1)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    is_active: bool = True


class ProductionInterruptionImpactConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plant_id: int
    material_id: int
    production_line_id: int | None = None
    production_rate_mt_per_hour: Decimal = Field(ge=0)
    finished_goods_value_per_mt: Decimal = Field(ge=0)
    survivable_hours_without_material: Decimal = Field(ge=0)
    line_dependency_ratio: Decimal = Field(ge=0, le=1)
    downtime_cost_per_hour: Decimal = Field(ge=0)
    restart_cost: Decimal = Field(ge=0)
    restart_time_hours: Decimal = Field(ge=0)
    substitution_factor: Decimal = Field(ge=0, le=1)
    cascading_impact_factor: Decimal = Field(ge=0)
    interruption_probability_override: Decimal | None = Field(default=None, ge=0, le=1)
    currency: str = "INR"
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ContinuityThresholdPayload(BaseModel):
    plant_id: int
    material_id: int
    warning_days: Decimal = Field(ge=0)
    threshold_days: Decimal = Field(ge=0)
    minimum_buffer_stock_days: Decimal | None = Field(default=None, ge=0)
    minimum_buffer_stock_mt: Decimal | None = Field(default=None, ge=0)
    reserve_quantity_mt: Decimal | None = Field(default=None, ge=0)
    quality_hold_quantity_mt: Decimal | None = Field(default=None, ge=0)
    stockout_alert_horizon_days: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def warning_must_not_be_less_than_critical(self):
        if self.warning_days < self.threshold_days:
            raise ValueError("warning_days must be greater than or equal to threshold_days")
        return self


class ContinuityThresholdRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plant_id: int
    material_id: int
    warning_days: Decimal = Field(ge=0)
    threshold_days: Decimal = Field(ge=0)
    minimum_buffer_stock_days: Decimal | None = Field(default=None, ge=0)
    minimum_buffer_stock_mt: Decimal | None = Field(default=None, ge=0)
    reserve_quantity_mt: Decimal | None = Field(default=None, ge=0)
    quality_hold_quantity_mt: Decimal | None = Field(default=None, ge=0)
    stockout_alert_horizon_days: Decimal | None = Field(default=None, ge=0)
    created_at: datetime
    updated_at: datetime


class ProductionLinePayload(BaseModel):
    plant_id: int
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=255)
    is_active: bool = True


class ProductionLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plant_id: int
    code: str
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProcessProductDependencyPayload(BaseModel):
    process_id: int
    product_name: str = Field(min_length=1, max_length=255)
    output_share_ratio: Decimal = Field(ge=0, le=1)
    product_value_per_mt: Decimal = Field(ge=0)
    operational_criticality_factor: Decimal = Field(ge=0, le=2)
    is_active: bool = True


class ProcessProductDependencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    process_id: int
    product_name: str
    output_share_ratio: Decimal = Field(ge=0, le=1)
    product_value_per_mt: Decimal = Field(ge=0)
    operational_criticality_factor: Decimal = Field(ge=0, le=2)
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MaterialProcessDependencyPayload(BaseModel):
    material_id: int
    process_id: int
    dependency_ratio: Decimal = Field(ge=0, le=1)
    substitution_factor: Decimal | None = Field(default=None, ge=0, le=1)
    survivability_hours: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True


class MaterialProcessDependencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    process_id: int
    dependency_ratio: Decimal = Field(ge=0, le=1)
    substitution_factor: Decimal | None = Field(default=None, ge=0, le=1)
    survivability_hours: Decimal | None = Field(default=None, ge=0)
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ShipmentInboundTrustConfigPayload(BaseModel):
    plant_id: int
    material_id: int
    visibility_profile: str
    expected_visibility_cadence_hours: Decimal = Field(ge=0)
    eta_drift_tolerance_hours: Decimal = Field(ge=0)
    weak_visibility_threshold: Decimal = Field(ge=0, le=1)
    minimum_trusted_inbound_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    allow_unverified_inbound_protection: bool = False
    is_active: bool = True

    @field_validator("visibility_profile")
    @classmethod
    def visibility_profile_must_be_known(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in VISIBILITY_PROFILES:
            raise ValueError("visibility_profile must be one of the supported profiles")
        return normalized


class ShipmentInboundTrustConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plant_id: int
    material_id: int
    visibility_profile: str
    expected_visibility_cadence_hours: Decimal = Field(ge=0)
    eta_drift_tolerance_hours: Decimal = Field(ge=0)
    weak_visibility_threshold: Decimal = Field(ge=0, le=1)
    minimum_trusted_inbound_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    allow_unverified_inbound_protection: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OperationalInterruptionImpact(BaseModel):
    material_exposure_value: Decimal | None = None
    operational_interruption_impact: Decimal | None = None
    calculation_status: str
    currency: str
    estimated_interruption_hours: Decimal | None = None
    interruption_probability: Decimal | None = None
    gross_production_impact: Decimal | None = None
    downtime_impact: Decimal | None = None
    restart_impact: Decimal | None = None
    cascading_impact_factor: Decimal | None = None
    gross_operational_impact: Decimal | None = None
    final_estimated_impact: Decimal | None = None
    missing_config_fields: list[str]
    formula_version: str
    reason_chain: list[str]
