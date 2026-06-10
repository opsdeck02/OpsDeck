"""Add separate threshold quantity fields.

Revision ID: 0023
Revises: 0022_cleanup_legacy_demo_seed_data
Create Date: 2026-06-10 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022_cleanup_legacy_demo_seed_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plant_material_thresholds",
        sa.Column("reserve_quantity_mt", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "plant_material_thresholds",
        sa.Column("quality_hold_quantity_mt", sa.Numeric(14, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plant_material_thresholds", "quality_hold_quantity_mt")
    op.drop_column("plant_material_thresholds", "reserve_quantity_mt")
