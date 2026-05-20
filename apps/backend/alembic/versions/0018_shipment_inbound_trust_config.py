"""shipment inbound trust config

Revision ID: 0018_shipment_inbound_trust_config
Revises: 0017
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_shipment_inbound_trust_config"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shipment_inbound_trust_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("visibility_profile", sa.String(length=20), nullable=False),
        sa.Column("expected_visibility_cadence_hours", sa.Numeric(10, 2), nullable=False),
        sa.Column("eta_drift_tolerance_hours", sa.Numeric(10, 2), nullable=False),
        sa.Column("weak_visibility_threshold", sa.Numeric(5, 4), nullable=False),
        sa.Column("minimum_trusted_inbound_ratio", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "allow_unverified_inbound_protection",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "expected_visibility_cadence_hours >= 0",
            name="ck_shipment_trust_cadence_gte_0",
        ),
        sa.CheckConstraint(
            "eta_drift_tolerance_hours >= 0",
            name="ck_shipment_trust_eta_tolerance_gte_0",
        ),
        sa.CheckConstraint(
            "weak_visibility_threshold >= 0 AND weak_visibility_threshold <= 1",
            name="ck_shipment_trust_weak_threshold_range",
        ),
        sa.CheckConstraint(
            "minimum_trusted_inbound_ratio IS NULL OR "
            "(minimum_trusted_inbound_ratio >= 0 AND minimum_trusted_inbound_ratio <= 1)",
            name="ck_shipment_trust_min_ratio_range",
        ),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_shipment_trust_tenant_plant_material_active",
        "shipment_inbound_trust_configs",
        ["tenant_id", "plant_id", "material_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_shipment_trust_tenant_plant_material_active",
        table_name="shipment_inbound_trust_configs",
    )
    op.drop_table("shipment_inbound_trust_configs")
