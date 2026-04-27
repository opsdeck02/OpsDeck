"""Add tenant access_weeks, is_active, and access_expires_at

Revision ID: 0003
Revises: 0002_superadmin_tenant_limits
Create Date: 2026-04-17 12:57:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002_superadmin_tenant_limits'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tenants', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('tenants', sa.Column('access_weeks', sa.Integer(), nullable=True))
    op.add_column('tenants', sa.Column('access_expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('tenants', 'access_expires_at')
    op.drop_column('tenants', 'access_weeks')
    op.drop_column('tenants', 'is_active')