"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-14 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def timestamp_columns() -> list[sa.Column]:
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
            nullable=False,
        ),
    ]


def ci(name: str, table_name: str, columns: list[str]) -> None:
    op.create_index(name, table_name, columns)


shipment_state = sa.Enum(
    "planned",
    "in_transit",
    "at_port",
    "discharging",
    "inland_transit",
    "delivered",
    "delayed",
    "cancelled",
    name="shipment_state",
)
exception_type = sa.Enum(
    "eta_risk",
    "stockout_risk",
    "demurrage_risk",
    "quality_hold",
    "documentation_gap",
    "data_quality",
    name="exception_type",
)
exception_severity = sa.Enum("low", "medium", "high", "critical", name="exception_severity")
exception_status = sa.Enum(
    "open",
    "acknowledged",
    "in_progress",
    "resolved",
    "dismissed",
    name="exception_status",
)


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_user"),
    )
    op.create_index(
        "ix_tenant_memberships_user_tenant",
        "tenant_memberships",
        ["user_id", "tenant_id"],
    )
    op.create_table(
        "plants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_plants_tenant_code"),
    )
    op.create_index("ix_plants_tenant_id", "plants", ["tenant_id"])
    op.create_table(
        "materials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("uom", sa.String(length=20), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_materials_tenant_code"),
    )
    op.create_index("ix_materials_tenant_id", "materials", ["tenant_id"])
    op.create_table(
        "plant_material_thresholds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("threshold_days", sa.Numeric(8, 2), nullable=False),
        sa.Column("warning_days", sa.Numeric(8, 2), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "plant_id",
            "material_id",
            name="uq_thresholds_tenant_plant_material",
        ),
    )
    ci(
        "ix_thresholds_tenant_material",
        "plant_material_thresholds",
        ["tenant_id", "material_id"],
    )
    ci("ix_thresholds_tenant_plant", "plant_material_thresholds", ["tenant_id", "plant_id"])
    op.create_table(
        "shipments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("shipment_id", sa.String(length=80), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("supplier_name", sa.String(length=255), nullable=False),
        sa.Column("quantity_mt", sa.Numeric(14, 3), nullable=False),
        sa.Column("vessel_name", sa.String(length=255), nullable=True),
        sa.Column("imo_number", sa.String(length=20), nullable=True),
        sa.Column("mmsi", sa.String(length=20), nullable=True),
        sa.Column("origin_port", sa.String(length=255), nullable=True),
        sa.Column("destination_port", sa.String(length=255), nullable=True),
        sa.Column("planned_eta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_eta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("eta_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("current_state", shipment_state, nullable=False),
        sa.Column("source_of_truth", sa.String(length=80), nullable=False),
        sa.Column("latest_update_at", sa.DateTime(timezone=True), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "shipment_id", name="uq_shipments_tenant_business_key"),
    )
    op.create_index("ix_shipments_imo_number", "shipments", ["imo_number"])
    op.create_index("ix_shipments_mmsi", "shipments", ["mmsi"])
    ci("ix_shipments_tenant_latest_update", "shipments", ["tenant_id", "latest_update_at"])
    ci(
        "ix_shipments_tenant_material_eta",
        "shipments",
        ["tenant_id", "material_id", "current_eta"],
    )
    ci(
        "ix_shipments_tenant_plant_state",
        "shipments",
        ["tenant_id", "plant_id", "current_state"],
    )
    op.create_table(
        "shipment_updates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    ci(
        "ix_shipment_updates_tenant_shipment_time",
        "shipment_updates",
        ["tenant_id", "shipment_id", "event_time"],
    )
    ci("ix_shipment_updates_tenant_source", "shipment_updates", ["tenant_id", "source"])
    op.create_table(
        "stock_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("on_hand_mt", sa.Numeric(14, 3), nullable=False),
        sa.Column("quality_held_mt", sa.Numeric(14, 3), nullable=False),
        sa.Column("available_to_consume_mt", sa.Numeric(14, 3), nullable=False),
        sa.Column("daily_consumption_mt", sa.Numeric(14, 3), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    ci(
        "ix_stock_snapshots_tenant_plant_material_time",
        "stock_snapshots",
        ["tenant_id", "plant_id", "material_id", "snapshot_time"],
    )
    op.create_table(
        "port_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("berth_status", sa.String(length=80), nullable=False),
        sa.Column("waiting_days", sa.Numeric(8, 2), nullable=False),
        sa.Column("discharge_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discharge_rate_mt_per_day", sa.Numeric(14, 3), nullable=True),
        sa.Column("estimated_demurrage_exposure", sa.Numeric(14, 2), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_port_events_tenant_shipment", "port_events", ["tenant_id", "shipment_id"])
    op.create_index("ix_port_events_tenant_status", "port_events", ["tenant_id", "berth_status"])
    op.create_table(
        "inland_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=40), nullable=False),
        sa.Column("carrier_name", sa.String(length=255), nullable=True),
        sa.Column("origin_location", sa.String(length=255), nullable=True),
        sa.Column("destination_location", sa.String(length=255), nullable=True),
        sa.Column("planned_departure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_arrival_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_departure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_arrival_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_state", sa.String(length=80), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    ci("ix_inland_movements_tenant_shipment", "inland_movements", ["tenant_id", "shipment_id"])
    ci("ix_inland_movements_tenant_state", "inland_movements", ["tenant_id", "current_state"])
    op.create_table(
        "exception_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("type", exception_type, nullable=False),
        sa.Column("severity", exception_severity, nullable=False),
        sa.Column("status", exception_status, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("linked_shipment_id", sa.Integer(), nullable=True),
        sa.Column("linked_plant_id", sa.Integer(), nullable=True),
        sa.Column("linked_material_id", sa.Integer(), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_action", sa.String(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["linked_material_id"], ["materials.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_plant_id"], ["plants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_shipment_id"], ["shipments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exception_cases_tenant_due_at", "exception_cases", ["tenant_id", "due_at"])
    ci("ix_exception_cases_tenant_owner", "exception_cases", ["tenant_id", "owner_user_id"])
    ci(
        "ix_exception_cases_tenant_status_severity",
        "exception_cases",
        ["tenant_id", "status", "severity"],
    )
    op.create_table(
        "exception_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("exception_case_id", sa.Integer(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=True),
        sa.Column("comment", sa.String(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["exception_case_id"], ["exception_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    ci(
        "ix_exception_comments_tenant_case",
        "exception_comments",
        ["tenant_id", "exception_case_id"],
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=False),
        sa.Column("metadata_json", sa.String(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_tenant_actor", "audit_logs", ["tenant_id", "actor_user_id"])
    ci("ix_audit_logs_tenant_entity", "audit_logs", ["tenant_id", "entity_type", "entity_id"])
    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_uri", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_uploaded_files_tenant_status", "uploaded_files", ["tenant_id", "status"])
    ci(
        "ix_uploaded_files_tenant_uploaded_by",
        "uploaded_files",
        ["tenant_id", "uploaded_by_user_id"],
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_file_id", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("records_total", sa.Integer(), nullable=False),
        sa.Column("records_succeeded", sa.Integer(), nullable=False),
        sa.Column("records_failed", sa.Integer(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_file_id"], ["uploaded_files.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    ci("ix_ingestion_jobs_tenant_source", "ingestion_jobs", ["tenant_id", "source_type"])
    op.create_index("ix_ingestion_jobs_tenant_status", "ingestion_jobs", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_table("ingestion_jobs")
    op.drop_table("uploaded_files")
    op.drop_table("audit_logs")
    op.drop_table("exception_comments")
    op.drop_table("exception_cases")
    op.drop_table("inland_movements")
    op.drop_table("port_events")
    op.drop_table("stock_snapshots")
    op.drop_table("shipment_updates")
    op.drop_table("shipments")
    op.drop_table("plant_material_thresholds")
    op.drop_table("materials")
    op.drop_table("plants")
    op.drop_index("ix_tenant_memberships_user_tenant", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_table("roles")
    op.drop_table("tenants")
    exception_status.drop(op.get_bind(), checkfirst=True)
    exception_severity.drop(op.get_bind(), checkfirst=True)
    exception_type.drop(op.get_bind(), checkfirst=True)
    shipment_state.drop(op.get_bind(), checkfirst=True)
