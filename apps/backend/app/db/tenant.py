from __future__ import annotations

from typing import TypeVar

from sqlalchemy import Select

T = TypeVar("T")


def tenant_select(statement: Select[T], model: type, tenant_id: int) -> Select[T]:
    """Apply the tenant boundary in one place for tenant-scoped reads.

    Existing service code already derives tenant_id from RequestContext. New queries should
    use this helper to make the tenant filter hard to forget.
    """

    if not hasattr(model, "tenant_id"):
        raise ValueError(f"{model.__name__} is not tenant scoped")
    return statement.where(model.tenant_id == tenant_id)
