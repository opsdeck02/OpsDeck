"""add superadmin support and tenant user limits

Revision ID: 0002_superadmin_tenant_limits
Revises: 0001_initial
Create Date: 2026-04-17 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_superadmin_tenant_limits"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("max_users", sa.Integer(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "is_superadmin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_superadmin")
    op.drop_column("tenants", "max_users")
