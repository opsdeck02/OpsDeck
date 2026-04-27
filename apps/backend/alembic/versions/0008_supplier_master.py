"""add supplier master

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-26 12:15:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
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
            onupdate=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("primary_port", sa.String(length=255), nullable=True),
        sa.Column("secondary_ports", sa.JSON(), nullable=True),
        sa.Column("material_categories", sa.JSON(), nullable=True),
        sa.Column("country_of_origin", sa.String(length=120), nullable=True),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_suppliers_tenant_name"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_suppliers_tenant_code"),
    )
    op.create_index("ix_suppliers_tenant_active", "suppliers", ["tenant_id", "is_active"])
    with op.batch_alter_table("shipments") as batch_op:
        batch_op.add_column(sa.Column("supplier_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_shipments_supplier_id_suppliers",
            "suppliers",
            ["supplier_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("shipments") as batch_op:
        batch_op.drop_constraint("fk_shipments_supplier_id_suppliers", type_="foreignkey")
        batch_op.drop_column("supplier_id")
    op.drop_index("ix_suppliers_tenant_active", table_name="suppliers")
    op.drop_table("suppliers")
