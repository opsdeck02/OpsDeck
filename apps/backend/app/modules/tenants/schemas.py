from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


TenantPlanTier = Literal["pilot", "paid", "enterprise"]
DataSourceType = Literal["google_sheets", "excel_online"]
DatasetType = Literal["shipments", "stock", "thresholds"]


class TenantAdminUserPayload(BaseModel):
    email: str
    full_name: str
    password: str = Field(min_length=8)


class TenantCreateRequest(BaseModel):
    name: str
    slug: str
    plan_tier: TenantPlanTier = "pilot"
    max_users: int | None = Field(default=None, ge=1)
    access_weeks: int | None = Field(default=None, ge=1, description="Number of weeks of access for the tenant")
    admin_user: TenantAdminUserPayload | None = None


class TenantSummaryOut(BaseModel):
    id: int
    name: str
    slug: str
    plan_tier: TenantPlanTier = "pilot"
    max_users: int | None
    is_active: bool = True
    access_weeks: int | None = None
    access_expires_at: datetime | None = None
    active_user_count: int | None = None
    created_at: datetime


class TenantCreatedResponse(BaseModel):
    id: int
    name: str
    slug: str
    plan_tier: TenantPlanTier = "pilot"
    max_users: int | None
    access_weeks: int | None = None
    created_at: datetime
    admin_user: dict | None = None


class TenantPlanSummaryOut(BaseModel):
    tenant_id: int
    tenant_name: str
    tenant_slug: str
    plan_tier: TenantPlanTier
    capabilities: dict[str, bool]


class TenantPlanUpdateRequest(BaseModel):
    plan_tier: TenantPlanTier


class ExternalDataSourceBase(BaseModel):
    source_type: DataSourceType
    source_url: str
    source_name: str
    dataset_type: DatasetType
    mapping_config: dict[str, Any] | None = None
    sync_frequency_minutes: int = Field(default=60, ge=5, le=10080)
    is_active: bool = True


class ExternalDataSourceCreateRequest(ExternalDataSourceBase):
    pass


class ExternalDataSourceUpdateRequest(ExternalDataSourceBase):
    pass


class ExternalDataSourceOut(BaseModel):
    id: int
    tenant_id: int
    source_type: DataSourceType
    source_url: str
    source_name: str
    dataset_type: DatasetType
    platform_detected: str | None = None
    mapping_config: dict[str, Any]
    sync_frequency_minutes: int
    is_active: bool
    last_sync_status: str | None
    last_synced_at: datetime | None
    last_error_message: str | None
    data_freshness_status: str
    data_freshness_age_minutes: int | None
    last_sync_summary: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ExternalDataSourceSyncResult(BaseModel):
    source_id: int
    sync_status: str
    rows_received: int
    rows_accepted: int
    rows_rejected: int
    validation_summary: dict[str, int]
    validation_errors: list[dict[str, Any]]
    last_error: str | None
    last_synced_at: datetime | None
    new_critical_risks_count: int
    resolved_risks_count: int
    newly_breached_actions_count: int
    data_freshness_status: str
    data_freshness_age_minutes: int | None
