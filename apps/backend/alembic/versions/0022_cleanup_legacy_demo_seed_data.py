"""cleanup legacy demo data

Revision ID: 0022_cleanup_demo_data
Revises: 0021_mark_demo_steel_tenant
Create Date: 2026-05-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_cleanup_demo_data"
down_revision: str | None = "0021_mark_demo_steel_tenant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tenant_filter = "select id from tenants where slug = 'demo-steel'"
    legacy_plants = (
        "select id from plants where tenant_id in ({tenant_filter}) "
        "and code in ('JAM', 'KAL')"
    ).format(tenant_filter=tenant_filter)
    legacy_shipments = (
        "select id from shipments where tenant_id in ({tenant_filter}) "
        "and (shipment_id in ("
        "'INB-PDP-COAL-117', 'RAKE-BRB-ORE-042', 'RAKE-DHM-LIME-014', "
        "'INB-HLD-DOLO-026', 'INB-VZG-PELLET-022'"
        ") or plant_id in ({legacy_plants}))"
    ).format(tenant_filter=tenant_filter, legacy_plants=legacy_plants)

    statements = [
        "delete from exception_comments where tenant_id in ({tenant_filter})".format(
            tenant_filter=tenant_filter
        ),
        "delete from exception_cases where tenant_id in ({tenant_filter})".format(
            tenant_filter=tenant_filter
        ),
        "delete from line_stop_incidents where tenant_id in ({tenant_filter})".format(
            tenant_filter=tenant_filter
        ),
        "delete from port_events where tenant_id in ({tenant_filter})".format(
            tenant_filter=tenant_filter
        ),
        "delete from inland_movements where tenant_id in ({tenant_filter})".format(
            tenant_filter=tenant_filter
        ),
        "delete from shipment_updates where tenant_id in ({tenant_filter})".format(
            tenant_filter=tenant_filter
        ),
        "delete from operational_events where tenant_id in ({tenant_filter})".format(
            tenant_filter=tenant_filter
        ),
        "delete from production_interruption_impact_configs where tenant_id in "
        "({tenant_filter}) and plant_id in ({legacy_plants})".format(
            tenant_filter=tenant_filter,
            legacy_plants=legacy_plants,
        ),
        "delete from plant_material_thresholds where tenant_id in ({tenant_filter}) "
        "and plant_id in ({legacy_plants})".format(
            tenant_filter=tenant_filter,
            legacy_plants=legacy_plants,
        ),
        "delete from stock_snapshots where tenant_id in ({tenant_filter}) "
        "and plant_id in ({legacy_plants})".format(
            tenant_filter=tenant_filter,
            legacy_plants=legacy_plants,
        ),
        "delete from shipments where id in ({legacy_shipments})".format(
            legacy_shipments=legacy_shipments
        ),
        "delete from external_data_sources where tenant_id in ({tenant_filter}) "
        "and source_name in ('Demo ERP inbound feed', 'Continuity inbound source feed')".format(
            tenant_filter=tenant_filter
        ),
    ]
    for statement in statements:
        op.execute(sa.text(statement))


def downgrade() -> None:
    # Legacy seeded rows are intentionally not recreated.
    pass
