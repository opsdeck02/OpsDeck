"""add container tracking

Revision ID: 0011_container_tracking
Revises: 0010_microsoft_integration
Create Date: 2026-05-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_container_tracking"
down_revision = "0010_microsoft_integration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shipments", sa.Column("latest_eta", sa.DateTime(timezone=True), nullable=True))
    op.add_column("shipments", sa.Column("delay_days", sa.Integer(), nullable=True))
    op.add_column(
        "shipments",
        sa.Column("delay_status", sa.String(length=20), nullable=False, server_default="unknown"),
    )
    op.add_column("shipments", sa.Column("current_milestone", sa.String(length=80), nullable=True))
    op.add_column("shipments", sa.Column("current_location", sa.String(length=255), nullable=True))
    op.add_column(
        "shipments",
        sa.Column("last_tracking_update_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "tracking_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider_type", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_tracking_sources_tenant_code"),
    )
    op.create_table(
        "containers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("container_no", sa.String(length=11), nullable=False),
        sa.Column("carrier_code", sa.String(length=40), nullable=True),
        sa.Column("tracking_source", sa.String(length=40), nullable=True),
        sa.Column("detection_confidence", sa.String(length=20), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "container_no", name="uq_containers_tenant_container_no"),
    )
    op.create_index("ix_containers_tenant_carrier", "containers", ["tenant_id", "carrier_code"])
    op.create_table(
        "shipment_containers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("container_id", sa.Integer(), nullable=False),
        sa.Column("carrier_code", sa.String(length=40), nullable=False),
        sa.Column("tracking_source", sa.String(length=40), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["container_id"], ["containers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "shipment_id",
            "container_id",
            name="uq_shipment_containers_tenant_link",
        ),
    )
    op.create_index(
        "ix_shipment_containers_tenant_container",
        "shipment_containers",
        ["tenant_id", "container_id"],
    )
    op.create_table(
        "tracking_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("container_id", sa.Integer(), nullable=False),
        sa.Column("shipment_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("event_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location_name", sa.String(length=255), nullable=True),
        sa.Column("location_code", sa.String(length=40), nullable=True),
        sa.Column("transport_mode", sa.String(length=20), nullable=False),
        sa.Column("vessel_name", sa.String(length=255), nullable=True),
        sa.Column("voyage_no", sa.String(length=80), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("raw_payload", sa.String(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["container_id"], ["containers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tracking_events_tenant_container_time",
        "tracking_events",
        ["tenant_id", "container_id", "event_datetime"],
    )
    op.create_index(
        "ix_tracking_events_tenant_shipment_time",
        "tracking_events",
        ["tenant_id", "shipment_id", "event_datetime"],
    )


def downgrade() -> None:
    op.drop_index("ix_tracking_events_tenant_shipment_time", table_name="tracking_events")
    op.drop_index("ix_tracking_events_tenant_container_time", table_name="tracking_events")
    op.drop_table("tracking_events")
    op.drop_index("ix_shipment_containers_tenant_container", table_name="shipment_containers")
    op.drop_table("shipment_containers")
    op.drop_index("ix_containers_tenant_carrier", table_name="containers")
    op.drop_table("containers")
    op.drop_table("tracking_sources")
    op.drop_column("shipments", "last_tracking_update_at")
    op.drop_column("shipments", "current_location")
    op.drop_column("shipments", "current_milestone")
    op.drop_column("shipments", "delay_status")
    op.drop_column("shipments", "delay_days")
    op.drop_column("shipments", "latest_eta")
