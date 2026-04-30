"""add microsoft graph integration

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-27 03:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "microsoft_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("microsoft_user_id", sa.String(length=255), nullable=False),
        sa.Column("microsoft_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("auth_error", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_token_refresh_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "microsoft_user_id", name="uq_microsoft_connections_tenant_user"),
    )
    op.create_index("ix_microsoft_connections_tenant_active", "microsoft_connections", ["tenant_id", "is_active"])

    op.create_table(
        "microsoft_oauth_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state", name="uq_microsoft_oauth_states_state"),
    )
    op.create_index("ix_microsoft_oauth_states_tenant_user", "microsoft_oauth_states", ["tenant_id", "user_id"])

    op.create_table(
        "microsoft_data_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("microsoft_connection_id", sa.Uuid(), nullable=False),
        sa.Column("drive_id", sa.String(length=255), nullable=False),
        sa.Column("item_id", sa.String(length=255), nullable=False),
        sa.Column("site_id", sa.String(length=255), nullable=True),
        sa.Column("file_type", sa.String(length=40), nullable=False),
        sa.Column("sheet_name", sa.String(length=255), nullable=True),
        sa.Column("column_mapping", sa.JSON(), nullable=True),
        sa.Column("sync_frequency_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("sync_status", sa.String(length=40), nullable=False, server_default="idle"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["microsoft_connection_id"], ["microsoft_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_microsoft_data_sources_tenant_active", "microsoft_data_sources", ["tenant_id", "is_active"])
    op.create_index("ix_microsoft_data_sources_due", "microsoft_data_sources", ["is_active", "sync_status"])


def downgrade() -> None:
    op.drop_index("ix_microsoft_data_sources_due", table_name="microsoft_data_sources")
    op.drop_index("ix_microsoft_data_sources_tenant_active", table_name="microsoft_data_sources")
    op.drop_table("microsoft_data_sources")
    op.drop_index("ix_microsoft_oauth_states_tenant_user", table_name="microsoft_oauth_states")
    op.drop_table("microsoft_oauth_states")
    op.drop_index("ix_microsoft_connections_tenant_active", table_name="microsoft_connections")
    op.drop_table("microsoft_connections")
