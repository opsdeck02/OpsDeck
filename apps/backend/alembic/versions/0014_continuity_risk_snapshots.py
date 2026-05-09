"""add continuity risk snapshots

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-09 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
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
            onupdate=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "continuity_risk_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("risk_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("risk_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=30), nullable=False),
        sa.Column("plant_reference", sa.String(length=255), nullable=True),
        sa.Column("material_reference", sa.String(length=255), nullable=True),
        sa.Column("shipment_reference", sa.String(length=255), nullable=True),
        sa.Column("supplier_reference", sa.String(length=255), nullable=True),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("days_of_cover", sa.Numeric(14, 4), nullable=True),
        sa.Column("projected_exhaustion_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exposure_level", sa.String(length=40), nullable=True),
        sa.Column("exposure_basis", sa.String(length=80), nullable=True),
        sa.Column("exposure_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("shipment_delay_hours", sa.Numeric(14, 2), nullable=True),
        sa.Column("tracking_freshness_minutes", sa.Numeric(14, 2), nullable=True),
        sa.Column("freshness_status", sa.String(length=40), nullable=True),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("usable_stock", sa.Numeric(14, 3), nullable=True),
        sa.Column("blocked_stock", sa.Numeric(14, 3), nullable=True),
        sa.Column("incoming_quantity", sa.Numeric(14, 3), nullable=True),
        sa.Column("escalation_state", sa.String(length=40), nullable=True),
        sa.Column("escalation_score", sa.Numeric(8, 2), nullable=True),
        sa.Column("escalation_reason", sa.Text(), nullable=True),
        sa.Column("source_event_ids", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "risk_fingerprint",
            "snapshot_time",
            name="uq_continuity_risk_snapshots_tenant_fingerprint_time",
        ),
    )
    op.create_index(
        "ix_continuity_risk_snapshots_tenant_fingerprint_time",
        "continuity_risk_snapshots",
        ["tenant_id", "risk_fingerprint", "snapshot_time"],
    )
    op.create_index(
        "ix_continuity_risk_snapshots_tenant_context",
        "continuity_risk_snapshots",
        ["tenant_id", "plant_reference", "material_reference", "shipment_reference"],
    )
    op.create_index(
        "ix_continuity_risk_snapshots_tenant_type_severity",
        "continuity_risk_snapshots",
        ["tenant_id", "risk_type", "severity"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_continuity_risk_snapshots_tenant_type_severity",
        table_name="continuity_risk_snapshots",
    )
    op.drop_index(
        "ix_continuity_risk_snapshots_tenant_context",
        table_name="continuity_risk_snapshots",
    )
    op.drop_index(
        "ix_continuity_risk_snapshots_tenant_fingerprint_time",
        table_name="continuity_risk_snapshots",
    )
    op.drop_table("continuity_risk_snapshots")
