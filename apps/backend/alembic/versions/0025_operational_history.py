"""Add tenant operational history.

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_operational_milestones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("milestone_type", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_operational_milestones_tenant",
        "tenant_operational_milestones",
        ["tenant_id"],
    )

    op.create_table(
        "tenant_operational_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("note_type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("attendees", sa.JSON(), nullable=True),
        sa.Column("actions", sa.JSON(), nullable=True),
        sa.Column("note_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_operational_notes_tenant",
        "tenant_operational_notes",
        ["tenant_id"],
    )

    op.create_table(
        "tenant_report_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_type", sa.String(length=30), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("snapshot_payload", sa.JSON(), nullable=False),
        sa.Column("pdf_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("generated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tenant_report_snapshots_tenant",
        "tenant_report_snapshots",
        ["tenant_id"],
    )
    op.create_index(
        "ix_tenant_report_snapshots_period",
        "tenant_report_snapshots",
        ["tenant_id", "report_type", "period_start", "period_end", "version"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_report_snapshots_period", table_name="tenant_report_snapshots")
    op.drop_index("ix_tenant_report_snapshots_tenant", table_name="tenant_report_snapshots")
    op.drop_table("tenant_report_snapshots")
    op.drop_index("ix_operational_notes_tenant", table_name="tenant_operational_notes")
    op.drop_table("tenant_operational_notes")
    op.drop_index(
        "ix_operational_milestones_tenant",
        table_name="tenant_operational_milestones",
    )
    op.drop_table("tenant_operational_milestones")
