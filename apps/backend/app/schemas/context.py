from pydantic import BaseModel


class RequestContext(BaseModel):
    tenant_id: int
    tenant_slug: str
    role: str
    user_id: int
