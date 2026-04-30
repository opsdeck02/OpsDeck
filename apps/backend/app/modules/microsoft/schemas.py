from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class MicrosoftAuthUrlOut(BaseModel):
    auth_url: str
    state: str


class MicrosoftConnectionOut(BaseModel):
    id: uuid.UUID
    tenant_id: int
    microsoft_user_id: str
    microsoft_tenant_id: str
    display_name: str
    email: str
    scope: str
    auth_error: str | None
    is_active: bool
    connected_at: datetime
    last_token_refresh_at: datetime | None

    model_config = {"from_attributes": True}


class MicrosoftFileOut(BaseModel):
    item_id: str
    drive_id: str
    name: str
    size: int | None = None
    modified_at: str | None = None
    web_url: str | None = None
    is_sharepoint: bool = False


class MicrosoftSharePointSiteOut(BaseModel):
    site_id: str
    name: str
    display_name: str


class MicrosoftDriveOut(BaseModel):
    drive_id: str
    name: str


class MicrosoftSheetNamesOut(BaseModel):
    sheet_names: list[str]


class MicrosoftDataSourceCreate(BaseModel):
    connection_id: uuid.UUID
    drive_id: str
    item_id: str
    site_id: str | None = None
    file_type: Literal["shipment", "stock", "threshold"]
    sheet_name: str | None = None
    column_mapping: dict[str, str] | None = None
    sync_frequency_minutes: int = Field(default=60, ge=15)
    display_name: str | None = None


class MicrosoftDataSourceUpdate(BaseModel):
    sheet_name: str | None = None
    column_mapping: dict[str, str] | None = None
    sync_frequency_minutes: int | None = Field(default=None, ge=15)
    is_active: bool | None = None
    display_name: str | None = None


class MicrosoftDataSourceOut(BaseModel):
    id: uuid.UUID
    tenant_id: int
    microsoft_connection_id: uuid.UUID
    drive_id: str
    item_id: str
    site_id: str | None
    file_type: str
    sheet_name: str | None
    column_mapping: dict[str, Any] | None
    sync_frequency_minutes: int
    last_successful_sync_at: datetime | None
    last_sync_attempted_at: datetime | None
    last_sync_error: str | None
    sync_status: str
    is_active: bool
    display_name: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MicrosoftSyncResult(BaseModel):
    rows_ingested: int
    file_type: str
    status: str
    detail: dict[str, Any] = Field(default_factory=dict)
