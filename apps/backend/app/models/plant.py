from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TenantScopedMixin, TimestampMixin


class Plant(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "plants"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_plants_tenant_code"),
        Index("ix_plants_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))

