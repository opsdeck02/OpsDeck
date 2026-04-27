"""add external source platform

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-27 02:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("external_data_sources") as batch_op:
        batch_op.add_column(sa.Column("platform_detected", sa.String(length=40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("external_data_sources") as batch_op:
        batch_op.drop_column("platform_detected")
