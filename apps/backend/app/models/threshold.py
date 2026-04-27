from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TenantScopedMixin, TimestampMixin


class PlantMaterialThreshold(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "plant_material_thresholds"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "plant_id",
            "material_id",
            name="uq_thresholds_tenant_plant_material",
        ),
        Index("ix_thresholds_tenant_plant", "tenant_id", "plant_id"),
        Index("ix_thresholds_tenant_material", "tenant_id", "material_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id", ondelete="CASCADE"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"))
    threshold_days: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    warning_days: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
