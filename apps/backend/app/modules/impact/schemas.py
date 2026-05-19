from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    stockout_alert_horizon_days: Decimal | None = Field(default=None, ge=0)
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
