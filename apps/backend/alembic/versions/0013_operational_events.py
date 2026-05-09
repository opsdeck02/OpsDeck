"""add operational events

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-09 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
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


def enum_values(*values: str, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False)


def upgrade() -> None:
    op.create_table(
        "operational_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column(
            "event_type",
            enum_values(
                "inventory_stock_updated",
                "inventory_below_threshold_signal",
                "inventory_quality_hold_updated",
                "shipment_eta_changed",
                "shipment_milestone_updated",
                "shipment_delay_detected",
                "shipment_linked_to_po",
                "supplier_commitment_changed",
                "planning_consumption_updated",
                "production_exposure_signal",
                "data_source_synced",
                "data_source_stale_signal",
                "manual_operational_note",
                name="operational_event_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "event_category",
            enum_values(
                "inventory",
                "shipment",
                "supplier",
                "planning",
                "production",
                "data_quality",
                "manual",
                "system",
                name="operational_event_category",
            ),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            enum_values(
                "manual_upload",
                "external_data_source",
                "erp",
                "wms",
                "tms",
                "ais",
                "email_ingestion",
                "file_ingestion",
                "supplier_update",
                "system",
                "manual",
                "unknown",
                name="operational_event_source_type",
            ),
            nullable=False,
        ),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=True),
        sa.Column("plant_reference", sa.String(length=255), nullable=True),
        sa.Column("material_id", sa.Integer(), nullable=True),
        sa.Column("material_reference", sa.String(length=255), nullable=True),
        sa.Column("shipment_id", sa.Integer(), nullable=True),
        sa.Column("shipment_reference", sa.String(length=255), nullable=True),
        sa.Column("supplier_id", sa.Uuid(), nullable=True),
        sa.Column("supplier_reference", sa.String(length=255), nullable=True),
        sa.Column("purchase_order_reference", sa.String(length=120), nullable=True),
        sa.Column("quantity_value", sa.Numeric(14, 3), nullable=True),
        sa.Column("quantity_unit", sa.String(length=20), nullable=True),
        sa.Column("previous_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "freshness_status",
            enum_values(
                "fresh",
                "delayed",
                "stale",
                "critical",
                "unknown",
                name="operational_event_freshness_status",
            ),
            nullable=True,
        ),
        *timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_operational_events_tenant_occurred",
        "operational_events",
        ["tenant_id", "occurred_at"],
    )
    op.create_index(
        "ix_operational_events_tenant_type",
        "operational_events",
        ["tenant_id", "event_type"],
    )
    op.create_index(
        "ix_operational_events_tenant_category",
        "operational_events",
        ["tenant_id", "event_category"],
    )
    op.create_index(
        "ix_operational_events_tenant_source",
        "operational_events",
        ["tenant_id", "source_type", "source_id"],
    )
    op.create_index(
        "ix_operational_events_tenant_plant_material",
        "operational_events",
        ["tenant_id", "plant_id", "material_id"],
    )
    op.create_index(
        "ix_operational_events_tenant_shipment",
        "operational_events",
        ["tenant_id", "shipment_id"],
    )
    op.create_index(
        "ix_operational_events_tenant_supplier",
        "operational_events",
        ["tenant_id", "supplier_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_operational_events_tenant_supplier", table_name="operational_events")
    op.drop_index("ix_operational_events_tenant_shipment", table_name="operational_events")
    op.drop_index("ix_operational_events_tenant_plant_material", table_name="operational_events")
    op.drop_index("ix_operational_events_tenant_source", table_name="operational_events")
    op.drop_index("ix_operational_events_tenant_category", table_name="operational_events")
    op.drop_index("ix_operational_events_tenant_type", table_name="operational_events")
    op.drop_index("ix_operational_events_tenant_occurred", table_name="operational_events")
    op.drop_table("operational_events")
