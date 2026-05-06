"""add tenant plant limits

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-06 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("max_plants", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "max_plants")
