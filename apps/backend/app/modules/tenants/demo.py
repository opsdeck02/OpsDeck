from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Tenant

PILOT_SCENARIOS_CAPABILITY = "pilot_scenarios"


def is_demo_tenant(db: Session, tenant_id: int) -> bool:
    tenant = db.get(Tenant, tenant_id)
    return bool(tenant and tenant.is_demo_tenant)


def add_demo_capabilities(capabilities: dict[str, bool], *, is_demo: bool) -> dict[str, bool]:
    return {
        **capabilities,
        PILOT_SCENARIOS_CAPABILITY: is_demo,
    }
