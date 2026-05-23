"""import job auditability

Revision ID: 0019_import_job_auditability
Revises: 0018_shipment_trust
Create Date: 2026-05-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_import_job_auditability"
down_revision: str | None = "0018_shipment_trust"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ingestion_jobs", sa.Column("stage", sa.String(length=80), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("metadata", sa.JSON(), nullable=True))
    op.create_table(
        "import_job_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("import_job_id", sa.Integer(), nullable=False),
        sa.Column("record_type", sa.String(length=80), nullable=False),
        sa.Column("record_id", sa.String(length=120), nullable=False),
        sa.Column("record_reference", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("rollback_safe", sa.Boolean(), nullable=False),
        sa.Column("rollback_status", sa.String(length=40), nullable=True),
        sa.Column("previous_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["import_job_id"], ["ingestion_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_import_job_records_tenant_job",
        "import_job_records",
        ["tenant_id", "import_job_id"],
    )
    op.create_index(
        "ix_import_job_records_tenant_record",
        "import_job_records",
        ["tenant_id", "record_type", "record_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_import_job_records_tenant_record", table_name="import_job_records")
    op.drop_index("ix_import_job_records_tenant_job", table_name="import_job_records")
    op.drop_table("import_job_records")
    op.drop_column("ingestion_jobs", "metadata")
    op.drop_column("ingestion_jobs", "stage")
