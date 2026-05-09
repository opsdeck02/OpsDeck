from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Material, Plant, Shipment, StockSnapshot, Tenant
from app.models.enums import (
    OperationalEventCategory,
    OperationalEventFreshnessStatus,
    OperationalEventSourceType,
    OperationalEventType,
    ShipmentState,
)
from app.modules.operational_events.schemas import OperationalEventCreate
from app.modules.operational_events.service import create_operational_event
from app.modules.relationships.graph import build_operational_relationship_graph
from app.schemas.context import RequestContext


def test_plant_material_lookup_returns_plant_and_material_nodes() -> None:
    with seeded_graph_session() as (db, tenant, plant, material, _):
        graph = build_operational_relationship_graph(
            db,
            context_for(tenant),
            plant_reference=plant.code,
            material_reference=material.code,
            now=NOW,
        )

        node_ids = {node.id for node in graph.nodes}
        assert node_ids.issuperset({"plant:P1", "material:M1"})
        assert edge_key("material:M1", "plant:P1", "used_at") in edge_keys(graph)


def test_shipment_lookup_returns_shipment_and_connected_material_plant() -> None:
    with seeded_graph_session() as (db, tenant, _, _, shipment):
        graph = build_operational_relationship_graph(
            db,
            context_for(tenant),
            shipment_reference=shipment.shipment_id,
            now=NOW,
        )

        node_ids = {node.id for node in graph.nodes}
        assert node_ids.issuperset({"shipment:SHIP-1", "material:M1", "plant:P1"})
        assert edge_key("shipment:SHIP-1", "material:M1", "replenishes") in edge_keys(graph)
        assert edge_key("shipment:SHIP-1", "plant:P1", "linked_to") in edge_keys(graph)


def test_edges_are_deterministic_and_not_duplicated() -> None:
    with seeded_graph_session() as (db, tenant, plant, material, shipment):
        create_event(
            db,
            tenant.id,
            plant_reference=plant.code,
            material_reference=material.code,
            shipment_reference=shipment.shipment_id,
        )
        db.commit()

        first = build_operational_relationship_graph(
            db,
            context_for(tenant),
            shipment_reference=shipment.shipment_id,
            now=NOW,
        )
        second = build_operational_relationship_graph(
            db,
            context_for(tenant),
            shipment_reference=shipment.shipment_id,
            now=NOW,
        )

        assert first.model_dump(mode="json") == second.model_dump(mode="json")
        assert len(edge_keys(first)) == len(first.edges)


def test_inventory_continuity_summary_is_included_for_plant_material_context() -> None:
    with seeded_graph_session() as (db, tenant, plant, material, _):
        graph = build_operational_relationship_graph(
            db,
            context_for(tenant),
            plant_reference=plant.code,
            material_reference=material.code,
            now=NOW,
        )

        assert graph.summary.inventory_continuity is not None
        assert graph.summary.inventory_continuity["plant_reference"] == "P1"
        assert graph.summary.inventory_continuity["material_reference"] == "M1"
        assert graph.summary.inventory_continuity["days_of_cover"] == Decimal("2.00")
        assert graph.summary.active_risk_candidate_count > 0


def test_shipment_continuity_summary_is_included_for_shipment_context() -> None:
    with seeded_graph_session() as (db, tenant, _, _, shipment):
        graph = build_operational_relationship_graph(
            db,
            context_for(tenant),
            shipment_reference=shipment.shipment_id,
            now=NOW,
        )

        assert graph.summary.shipment_continuity is not None
        assert graph.summary.shipment_continuity["shipment_reference"] == "SHIP-1"
        assert graph.summary.shipment_continuity["status"] == "degraded"


def test_relevant_timeline_event_count_is_included() -> None:
    with seeded_graph_session() as (db, tenant, plant, material, shipment):
        create_event(db, tenant.id, plant_reference=plant.code, material_reference=material.code)
        create_event(
            db,
            tenant.id,
            event_type=OperationalEventType.SHIPMENT_ETA_CHANGED,
            event_category=OperationalEventCategory.SHIPMENT,
            plant_reference=plant.code,
            material_reference=material.code,
            shipment_reference=shipment.shipment_id,
        )
        db.commit()

        graph = build_operational_relationship_graph(
            db,
            context_for(tenant),
            shipment_reference=shipment.shipment_id,
            now=NOW,
        )

        assert graph.summary.timeline_event_count == 2


def test_confidence_and_freshness_summary_is_included() -> None:
    with seeded_graph_session() as (db, tenant, plant, material, _):
        create_event(
            db,
            tenant.id,
            plant_reference=plant.code,
            material_reference=material.code,
            confidence_score=Decimal("40"),
            freshness_status=OperationalEventFreshnessStatus.STALE,
        )
        db.commit()

        graph = build_operational_relationship_graph(
            db,
            context_for(tenant),
            plant_reference=plant.code,
            material_reference=material.code,
            now=NOW,
        )

        assert graph.summary.confidence_summary.lowest_confidence_score == Decimal("40.00")
        assert graph.summary.confidence_summary.worst_freshness_status == "stale"


def test_relationship_graph_preserves_tenant_isolation() -> None:
    with seeded_graph_session() as (db, tenant_a, _, _, _):
        tenant_b = Tenant(name="Tenant B", slug="tenant-b")
        db.add(tenant_b)
        db.flush()
        plant_b = Plant(tenant_id=tenant_b.id, code="P2", name="Plant 2", location=None)
        material_b = Material(
            tenant_id=tenant_b.id,
            code="M2",
            name="Material 2",
            category="raw",
            uom="MT",
        )
        db.add_all([plant_b, material_b])
        db.flush()
        create_event(db, tenant_b.id, plant_reference="P2", material_reference="M2")
        db.commit()

        graph = build_operational_relationship_graph(
            db,
            context_for(tenant_a),
            plant_reference="P2",
            material_reference="M2",
            now=NOW,
        )

        assert graph.nodes == []
        assert graph.summary.timeline_event_count == 0


NOW = datetime(2026, 5, 9, 12, tzinfo=UTC)


class seeded_graph_session:
    def __enter__(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.session_local = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
        )
        Base.metadata.create_all(bind=self.engine)
        self.db = self.session_local()
        tenant = Tenant(name="Tenant A", slug="tenant-a")
        self.db.add(tenant)
        self.db.flush()
        plant = Plant(tenant_id=tenant.id, code="P1", name="Plant 1", location="North")
        material = Material(
            tenant_id=tenant.id,
            code="M1",
            name="Material 1",
            category="raw",
            uom="MT",
        )
        self.db.add_all([plant, material])
        self.db.flush()
        shipment = Shipment(
            tenant_id=tenant.id,
            shipment_id="SHIP-1",
            material_id=material.id,
            plant_id=plant.id,
            supplier_name="Supplier 1",
            quantity_mt=Decimal("50"),
            planned_eta=NOW + timedelta(days=1),
            current_eta=NOW + timedelta(days=4),
            latest_eta=NOW + timedelta(days=1),
            current_milestone="in_transit",
            last_tracking_update_at=NOW - timedelta(hours=8),
            current_state=ShipmentState.IN_TRANSIT,
            source_of_truth="manual_upload",
            latest_update_at=NOW - timedelta(hours=8),
        )
        self.db.add_all(
            [
                shipment,
                StockSnapshot(
                    tenant_id=tenant.id,
                    plant_id=plant.id,
                    material_id=material.id,
                    on_hand_mt=Decimal("20"),
                    quality_held_mt=Decimal("0"),
                    available_to_consume_mt=Decimal("20"),
                    daily_consumption_mt=Decimal("10"),
                    snapshot_time=NOW,
                ),
            ]
        )
        self.db.commit()
        return self.db, tenant, plant, material, shipment

    def __exit__(self, exc_type, exc_value, traceback):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)


def create_event(
    db: Session,
    tenant_id: int,
    *,
    event_type: OperationalEventType = OperationalEventType.INVENTORY_STOCK_UPDATED,
    event_category: OperationalEventCategory = OperationalEventCategory.INVENTORY,
    plant_reference: str | None = "P1",
    material_reference: str | None = "M1",
    shipment_reference: str | None = None,
    confidence_score: Decimal | None = None,
    freshness_status: OperationalEventFreshnessStatus | None = None,
):
    return create_operational_event(
        db,
        OperationalEventCreate(
            tenant_id=tenant_id,
            event_type=event_type,
            event_category=event_category,
            source_type=OperationalEventSourceType.FILE_INGESTION,
            source_reference="file_ingestion",
            occurred_at=NOW,
            detected_at=NOW,
            plant_reference=plant_reference,
            material_reference=material_reference,
            shipment_reference=shipment_reference,
            quantity_value=Decimal("20"),
            quantity_unit="MT",
            new_value={"available_to_consume_mt": "20"},
            confidence_score=confidence_score,
            freshness_status=freshness_status,
        ),
    )


def context_for(tenant: Tenant) -> RequestContext:
    return RequestContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        role="tenant_admin",
        user_id=1,
    )


def edge_key(from_node_id: str, to_node_id: str, relationship: str) -> tuple[str, str, str]:
    return (from_node_id, to_node_id, relationship)


def edge_keys(graph) -> set[tuple[str, str, str]]:
    return {
        (edge.from_node_id, edge.to_node_id, edge.relationship)
        for edge in graph.edges
    }
