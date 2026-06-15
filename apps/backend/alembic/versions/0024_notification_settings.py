"""Add notification settings and delivery logs.

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("critical_alerts_enabled", sa.Boolean(), nullable=False),
        sa.Column("weekly_digest_enabled", sa.Boolean(), nullable=False),
        sa.Column("recipients_to", sa.JSON(), nullable=False),
        sa.Column("recipients_cc", sa.JSON(), nullable=False),
        sa.Column("pilot_contacts", sa.JSON(), nullable=False),
        sa.Column("digest_day", sa.String(length=16), nullable=False),
        sa.Column("digest_time", sa.String(length=8), nullable=False),
        sa.Column("tenant_timezone", sa.String(length=80), nullable=False),
        sa.Column("cooldown_hours", sa.Integer(), nullable=False),
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
        sa.UniqueConstraint("tenant_id", name="uq_notification_settings_tenant"),
    )
    op.create_table(
        "notification_delivery_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("notification_type", sa.String(length=40), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("condition_key", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
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
        "ix_notification_logs_tenant_sent_at",
        "notification_delivery_logs",
        ["tenant_id", "sent_at"],
    )
    op.create_index(
        "ix_notification_logs_tenant_alert_key",
        "notification_delivery_logs",
        ["tenant_id", "notification_type", "condition_key", "sent_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_logs_tenant_alert_key", table_name="notification_delivery_logs")
    op.drop_index("ix_notification_logs_tenant_sent_at", table_name="notification_delivery_logs")
    op.drop_table("notification_delivery_logs")
    op.drop_table("notification_settings")
