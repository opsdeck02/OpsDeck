"""add product and process dependency modeling

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-20 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
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
        "process_product_dependencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("output_share_ratio", sa.Numeric(5, 4), nullable=False),
        sa.Column("product_value_per_mt", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "operational_criticality_factor",
            sa.Numeric(5, 4),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.CheckConstraint(
            "output_share_ratio >= 0 AND output_share_ratio <= 1",
            name="ck_process_product_output_share_range",
        ),
        sa.CheckConstraint(
            "product_value_per_mt >= 0",
            name="ck_process_product_value_gte_0",
        ),
        sa.CheckConstraint(
            "operational_criticality_factor >= 0 AND operational_criticality_factor <= 2",
            name="ck_process_product_criticality_range",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["process_id"], ["production_lines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_process_products_tenant_process_active",
        "process_product_dependencies",
        ["tenant_id", "process_id", "is_active"],
    )

    op.create_table(
        "material_process_dependencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("dependency_ratio", sa.Numeric(5, 4), nullable=False),
        sa.Column("substitution_factor", sa.Numeric(5, 4), nullable=True),
        sa.Column("survivability_hours", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.CheckConstraint(
            "dependency_ratio >= 0 AND dependency_ratio <= 1",
            name="ck_material_process_dependency_ratio_range",
        ),
        sa.CheckConstraint(
            "substitution_factor IS NULL OR "
            "(substitution_factor >= 0 AND substitution_factor <= 1)",
            name="ck_material_process_substitution_range",
        ),
        sa.CheckConstraint(
            "survivability_hours IS NULL OR survivability_hours >= 0",
            name="ck_material_process_survivability_gte_0",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["process_id"], ["production_lines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_material_process_tenant_material_active",
        "material_process_dependencies",
        ["tenant_id", "material_id", "is_active"],
    )
    op.create_index(
        "ix_material_process_tenant_process",
        "material_process_dependencies",
        ["tenant_id", "process_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_material_process_tenant_process",
        table_name="material_process_dependencies",
    )
    op.drop_index(
        "ix_material_process_tenant_material_active",
        table_name="material_process_dependencies",
    )
    op.drop_table("material_process_dependencies")
    op.drop_index(
        "ix_process_products_tenant_process_active",
        table_name="process_product_dependencies",
    )
    op.drop_table("process_product_dependencies")
