"""add action execution fields to exception cases

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-20 10:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exception_cases",
        sa.Column("action_status", sa.String(length=20), nullable=False, server_default="pending"),
    )
    op.add_column(
        "exception_cases",
        sa.Column("action_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "exception_cases",
        sa.Column("action_completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("exception_cases", "action_completed_at")
    op.drop_column("exception_cases", "action_started_at")
    op.drop_column("exception_cases", "action_status")
