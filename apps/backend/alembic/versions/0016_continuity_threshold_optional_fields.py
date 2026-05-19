"""Add optional continuity threshold fields.

Revision ID: 0016_continuity_threshold_optional_fields
Revises: 0015
Create Date: 2026-05-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_continuity_threshold_optional_fields"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plant_material_thresholds",
        sa.Column("minimum_buffer_stock_days", sa.Numeric(8, 2), nullable=True),
    )
    op.add_column(
        "plant_material_thresholds",
        sa.Column("minimum_buffer_stock_mt", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "plant_material_thresholds",
        sa.Column("stockout_alert_horizon_days", sa.Numeric(8, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plant_material_thresholds", "stockout_alert_horizon_days")
    op.drop_column("plant_material_thresholds", "minimum_buffer_stock_mt")
    op.drop_column("plant_material_thresholds", "minimum_buffer_stock_days")
