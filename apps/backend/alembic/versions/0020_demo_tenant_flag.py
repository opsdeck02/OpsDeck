"""demo tenant flag

Revision ID: 0020_demo_tenant_flag
Revises: 0019_import_job_auditability
Create Date: 2026-05-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_demo_tenant_flag"
down_revision: str | None = "0019_import_job_auditability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "is_demo_tenant",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "is_demo_tenant")
