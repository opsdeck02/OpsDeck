from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TimestampMixin


class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_suppliers_tenant_name"),
        UniqueConstraint("tenant_id", "code", name="uq_suppliers_tenant_code"),
        Index("ix_suppliers_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    primary_port: Mapped[str | None] = mapped_column(String(255))
    secondary_ports: Mapped[list[str] | None] = mapped_column(JSON)
    material_categories: Mapped[list[str] | None] = mapped_column(JSON)
    country_of_origin: Mapped[str | None] = mapped_column(String(120))
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
