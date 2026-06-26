"""Add weekly operational reviews.

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_weekly_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("review_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_title", sa.String(length=255), nullable=False),
        sa.Column("attendees", sa.JSON(), nullable=False),
        sa.Column("meeting_summary", sa.Text(), nullable=True),
        sa.Column("operational_observations", sa.JSON(), nullable=False),
        sa.Column("customer_feedback", sa.Text(), nullable=True),
        sa.Column("agreed_actions", sa.JSON(), nullable=False),
        sa.Column("blockers", sa.Text(), nullable=True),
        sa.Column("next_focus", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenant_weekly_reviews_tenant", "tenant_weekly_reviews", ["tenant_id"])
    op.create_index(
        "ix_tenant_weekly_reviews_tenant_week",
        "tenant_weekly_reviews",
        ["tenant_id", "week_number"],
    )

    op.create_table(
        "tenant_review_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("weekly_review_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(length=120), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(
            ["weekly_review_id"],
            ["tenant_weekly_reviews.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tenant_review_actions_weekly_review",
        "tenant_review_actions",
        ["weekly_review_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_review_actions_weekly_review",
        table_name="tenant_review_actions",
    )
    op.drop_table("tenant_review_actions")
    op.drop_index("ix_tenant_weekly_reviews_tenant_week", table_name="tenant_weekly_reviews")
    op.drop_index("ix_tenant_weekly_reviews_tenant", table_name="tenant_weekly_reviews")
    op.drop_table("tenant_weekly_reviews")
