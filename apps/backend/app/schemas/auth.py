from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TenantMembershipOut(BaseModel):
    tenant_id: int
    tenant_name: str
    tenant_slug: str
    role: str


class CurrentUser(BaseModel):
    id: int
    email: str
    full_name: str
    is_superadmin: bool = False
    memberships: list[TenantMembershipOut]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: CurrentUser
