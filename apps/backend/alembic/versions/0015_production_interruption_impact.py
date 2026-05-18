"""add production interruption impact config

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-18 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "production_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_production_lines_tenant_plant",
        "production_lines",
        ["tenant_id", "plant_id"],
    )
    op.create_index(
        "ix_production_lines_tenant_code",
        "production_lines",
        ["tenant_id", "code"],
    )

    op.create_table(
        "production_interruption_impact_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("production_line_id", sa.Integer(), nullable=True),
        sa.Column("production_rate_mt_per_hour", sa.Numeric(14, 4), nullable=False),
        sa.Column("finished_goods_value_per_mt", sa.Numeric(18, 2), nullable=False),
        sa.Column("survivable_hours_without_material", sa.Numeric(10, 2), nullable=False),
        sa.Column("line_dependency_ratio", sa.Numeric(5, 4), nullable=False),
        sa.Column("downtime_cost_per_hour", sa.Numeric(18, 2), nullable=False),
        sa.Column("restart_cost", sa.Numeric(18, 2), nullable=False),
        sa.Column("restart_time_hours", sa.Numeric(10, 2), nullable=False),
        sa.Column("substitution_factor", sa.Numeric(5, 4), nullable=False),
        sa.Column(
            "cascading_impact_factor",
            sa.Numeric(8, 4),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column("interruption_probability_override", sa.Numeric(5, 4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.CheckConstraint(
            "production_rate_mt_per_hour >= 0", name="ck_pii_production_rate_gte_0"
        ),
        sa.CheckConstraint(
            "finished_goods_value_per_mt >= 0", name="ck_pii_finished_goods_value_gte_0"
        ),
        sa.CheckConstraint(
            "survivable_hours_without_material >= 0", name="ck_pii_survivable_hours_gte_0"
        ),
        sa.CheckConstraint(
            "line_dependency_ratio >= 0 AND line_dependency_ratio <= 1",
            name="ck_pii_line_dependency_ratio_range",
        ),
        sa.CheckConstraint("downtime_cost_per_hour >= 0", name="ck_pii_downtime_cost_gte_0"),
        sa.CheckConstraint("restart_cost >= 0", name="ck_pii_restart_cost_gte_0"),
        sa.CheckConstraint("restart_time_hours >= 0", name="ck_pii_restart_time_gte_0"),
        sa.CheckConstraint(
            "substitution_factor >= 0 AND substitution_factor <= 1",
            name="ck_pii_substitution_factor_range",
        ),
        sa.CheckConstraint("cascading_impact_factor >= 0", name="ck_pii_cascading_factor_gte_0"),
        sa.CheckConstraint(
            "interruption_probability_override IS NULL OR "
            "(interruption_probability_override >= 0 AND interruption_probability_override <= 1)",
            name="ck_pii_probability_override_range",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["production_line_id"], ["production_lines.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pii_configs_tenant_plant_material_active",
        "production_interruption_impact_configs",
        ["tenant_id", "plant_id", "material_id", "is_active"],
    )
    op.create_index(
        "ix_pii_configs_tenant_line",
        "production_interruption_impact_configs",
        ["tenant_id", "production_line_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pii_configs_tenant_line",
        table_name="production_interruption_impact_configs",
    )
    op.drop_index(
        "ix_pii_configs_tenant_plant_material_active",
        table_name="production_interruption_impact_configs",
    )
    op.drop_table("production_interruption_impact_configs")
    op.drop_index("ix_production_lines_tenant_code", table_name="production_lines")
    op.drop_index("ix_production_lines_tenant_plant", table_name="production_lines")
    op.drop_table("production_lines")
