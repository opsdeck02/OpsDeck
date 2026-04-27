"""add data source freshness summary fields

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-21 15:30:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "external_data_sources",
        sa.Column("new_critical_risks_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "external_data_sources",
        sa.Column("resolved_risks_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "external_data_sources",
        sa.Column("newly_breached_actions_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("external_data_sources", "newly_breached_actions_count")
    op.drop_column("external_data_sources", "resolved_risks_count")
    op.drop_column("external_data_sources", "new_critical_risks_count")
