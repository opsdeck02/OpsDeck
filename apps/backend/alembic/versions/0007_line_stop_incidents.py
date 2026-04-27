"""add line stop incidents

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-26 11:45:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def timestamp_columns() -> list[sa.Column]:
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
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "line_stop_incidents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_line_stop_incidents_tenant_stopped_at",
        "line_stop_incidents",
        ["tenant_id", "stopped_at"],
    )
    op.create_index(
        "ix_line_stop_incidents_tenant_plant_material",
        "line_stop_incidents",
        ["tenant_id", "plant_id", "material_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_line_stop_incidents_tenant_plant_material", table_name="line_stop_incidents")
    op.drop_index("ix_line_stop_incidents_tenant_stopped_at", table_name="line_stop_incidents")
    op.drop_table("line_stop_incidents")
