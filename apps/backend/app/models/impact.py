from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TenantScopedMixin, TimestampMixin


class ProductionLine(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "production_lines"
    __table_args__ = (
        Index("ix_production_lines_tenant_plant", "tenant_id", "plant_id"),
        Index("ix_production_lines_tenant_code", "tenant_id", "code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProductionInterruptionImpactConfig(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "production_interruption_impact_configs"
    __table_args__ = (
        CheckConstraint("production_rate_mt_per_hour >= 0", name="ck_pii_production_rate_gte_0"),
        CheckConstraint(
            "finished_goods_value_per_mt >= 0", name="ck_pii_finished_goods_value_gte_0"
        ),
        CheckConstraint(
            "survivable_hours_without_material >= 0", name="ck_pii_survivable_hours_gte_0"
        ),
        CheckConstraint(
            "line_dependency_ratio >= 0 AND line_dependency_ratio <= 1",
            name="ck_pii_line_dependency_ratio_range",
        ),
        CheckConstraint("downtime_cost_per_hour >= 0", name="ck_pii_downtime_cost_gte_0"),
        CheckConstraint("restart_cost >= 0", name="ck_pii_restart_cost_gte_0"),
        CheckConstraint("restart_time_hours >= 0", name="ck_pii_restart_time_gte_0"),
        CheckConstraint(
            "substitution_factor >= 0 AND substitution_factor <= 1",
            name="ck_pii_substitution_factor_range",
        ),
        CheckConstraint("cascading_impact_factor >= 0", name="ck_pii_cascading_factor_gte_0"),
        CheckConstraint(
            "interruption_probability_override IS NULL OR "
            "(interruption_probability_override >= 0 AND interruption_probability_override <= 1)",
            name="ck_pii_probability_override_range",
        ),
        Index(
            "ix_pii_configs_tenant_plant_material_active",
            "tenant_id",
            "plant_id",
            "material_id",
            "is_active",
        ),
        Index("ix_pii_configs_tenant_line", "tenant_id", "production_line_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id", ondelete="CASCADE"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"))
    production_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("production_lines.id", ondelete="SET NULL")
    )
    production_rate_mt_per_hour: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    finished_goods_value_per_mt: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    survivable_hours_without_material: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    line_dependency_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    downtime_cost_per_hour: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    restart_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    restart_time_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    substitution_factor: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    cascading_impact_factor: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, default=Decimal("1.0")
    )
    interruption_probability_override: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProcessProductDependency(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "process_product_dependencies"
    __table_args__ = (
        CheckConstraint(
            "output_share_ratio >= 0 AND output_share_ratio <= 1",
            name="ck_process_product_output_share_range",
        ),
        CheckConstraint(
            "product_value_per_mt >= 0",
            name="ck_process_product_value_gte_0",
        ),
        CheckConstraint(
            "operational_criticality_factor >= 0 AND operational_criticality_factor <= 2",
            name="ck_process_product_criticality_range",
        ),
        Index(
            "ix_process_products_tenant_process_active",
            "tenant_id",
            "process_id",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    process_id: Mapped[int] = mapped_column(ForeignKey("production_lines.id", ondelete="CASCADE"))
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    output_share_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    product_value_per_mt: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    operational_criticality_factor: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("1.0")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class MaterialProcessDependency(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "material_process_dependencies"
    __table_args__ = (
        CheckConstraint(
            "dependency_ratio >= 0 AND dependency_ratio <= 1",
            name="ck_material_process_dependency_ratio_range",
        ),
        CheckConstraint(
            "substitution_factor IS NULL OR "
            "(substitution_factor >= 0 AND substitution_factor <= 1)",
            name="ck_material_process_substitution_range",
        ),
        CheckConstraint(
            "survivability_hours IS NULL OR survivability_hours >= 0",
            name="ck_material_process_survivability_gte_0",
        ),
        Index(
            "ix_material_process_tenant_material_active",
            "tenant_id",
            "material_id",
            "is_active",
        ),
        Index(
            "ix_material_process_tenant_process",
            "tenant_id",
            "process_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"))
    process_id: Mapped[int] = mapped_column(ForeignKey("production_lines.id", ondelete="CASCADE"))
    dependency_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    substitution_factor: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    survivability_hours: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ShipmentInboundTrustConfig(TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "shipment_inbound_trust_configs"
    __table_args__ = (
        CheckConstraint(
            "expected_visibility_cadence_hours >= 0",
            name="ck_shipment_trust_cadence_gte_0",
        ),
        CheckConstraint(
            "eta_drift_tolerance_hours >= 0",
            name="ck_shipment_trust_eta_tolerance_gte_0",
        ),
        CheckConstraint(
            "weak_visibility_threshold >= 0 AND weak_visibility_threshold <= 1",
            name="ck_shipment_trust_weak_threshold_range",
        ),
        CheckConstraint(
            "minimum_trusted_inbound_ratio IS NULL OR "
            "(minimum_trusted_inbound_ratio >= 0 AND minimum_trusted_inbound_ratio <= 1)",
            name="ck_shipment_trust_min_ratio_range",
        ),
        Index(
            "ix_shipment_trust_tenant_plant_material_active",
            "tenant_id",
            "plant_id",
            "material_id",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id", ondelete="CASCADE"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"))
    visibility_profile: Mapped[str] = mapped_column(String(20), nullable=False)
    expected_visibility_cadence_hours: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    eta_drift_tolerance_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    weak_visibility_threshold: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    minimum_trusted_inbound_ratio: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    allow_unverified_inbound_protection: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
