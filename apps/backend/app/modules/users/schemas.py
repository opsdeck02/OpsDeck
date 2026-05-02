from datetime import datetime

from pydantic import BaseModel, Field


class TenantUserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    is_superadmin: bool
    tenant_id: int
    tenant_name: str
    tenant_slug: str
    created_at: datetime


class TenantUserCreateRequest(BaseModel):
    email: str
    full_name: str
    password: str = Field(min_length=10)
    role: str
    tenant_id: int | None = None
