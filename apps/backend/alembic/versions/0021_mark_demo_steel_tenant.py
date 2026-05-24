"""mark demo steel tenant

Revision ID: 0021_mark_demo_steel_tenant
Revises: 0020_demo_tenant_flag
Create Date: 2026-05-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_mark_demo_steel_tenant"
down_revision: str | None = "0020_demo_tenant_flag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tenants = sa.table(
        "tenants",
        sa.column("slug", sa.String()),
        sa.column("is_demo_tenant", sa.Boolean()),
    )
    op.execute(
        tenants.update()
        .where(tenants.c.slug == "demo-steel")
        .values(is_demo_tenant=True)
    )


def downgrade() -> None:
    tenants = sa.table(
        "tenants",
        sa.column("slug", sa.String()),
        sa.column("is_demo_tenant", sa.Boolean()),
    )
    op.execute(
        tenants.update()
        .where(tenants.c.slug == "demo-steel")
        .values(is_demo_tenant=False)
    )
