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
from app.modules.signal_engine.service import (
    get_risk_workspace,
    list_signal_risks,
)
from app.schemas.context import RequestContext

NOW = datetime(2026, 5, 9, 12, tzinfo=UTC)


def test_demo_scenario_healthy_flow_has_no_active_material_exposure() -> None:
    with demo_session() as (db, tenant):
        plant, material = add_context(db, tenant, "HEALTHY", "COAL-H")
        add_stock(db, tenant, plant, material, on_hand=Decimal("200"), daily=Decimal("10"))
        add_shipment(
            db,
            tenant,
            plant,
            material,
            shipment_id="SHIP-HEALTHY",
            current_eta=NOW + timedelta(days=3),
            planned_eta=NOW + timedelta(days=3),
            tracking_updated_at=NOW - timedelta(minutes=30),
        )
        add_event(db, tenant, plant_reference=plant.code, material_reference=material.code)
        db.commit()

        risks = list_signal_risks(db, context_for(tenant), now=NOW)
        assert not [
            risk
            for risk in risks
            if risk.plant_reference == plant.code
            and risk.material_reference == material.code
            and risk.severity in {"critical", "high", "medium"}
        ]
        workspace = get_risk_workspace(
            db,
            context_for(tenant),
            plant_reference=plant.code,
            material_reference=material.code,
            severity="critical",
            now=NOW,
        )
        assert workspace.empty is True
        assert workspace.model_dump(mode="json")


def test_demo_scenario_cover_collapse_generates_critical_exposure() -> None:
    with demo_session() as (db, tenant):
        plant, material = add_context(db, tenant, "JAM", "COKE")
        add_stock(db, tenant, plant, material, on_hand=Decimal("10"), daily=Decimal("10"))
        add_event(db, tenant, plant_reference=plant.code, material_reference=material.code)
        db.commit()

        workspace = get_risk_workspace(
            db,
            context_for(tenant),
            plant_reference=plant.code,
            material_reference=material.code,
            severity="critical",
            now=NOW,
        )

        assert workspace.empty is False
        assert workspace.selected_risk is not None
        assert workspace.selected_risk.risk_type == "days_of_cover_breach"
        assert workspace.selected_risk.severity == "critical"
        assert workspace.explainability is not None
        assert workspace.explainability.reason_chain
        assert workspace.exposure is not None
        assert workspace.exposure.exposure_level == "immediate"
        assert workspace.exposure.exposure_basis == "projected_stockout"
        assert workspace.timeline.total == 1
        assert workspace.inventory_continuity[0].days_of_cover == Decimal("1.00")
        assert workspace.context_graph is not None
        assert_graph_edges_have_nodes(workspace.context_graph)
        assert workspace.model_dump(mode="json")


def test_demo_scenario_delayed_inbound_generates_delay_against_cover() -> None:
    with demo_session() as (db, tenant):
        plant, material = add_context(db, tenant, "JAM", "PCI")
        shipment = add_shipment(
            db,
            tenant,
            plant,
            material,
            shipment_id="SHIP-DELAY",
            current_eta=NOW + timedelta(days=4),
            planned_eta=NOW + timedelta(days=1),
            tracking_updated_at=NOW - timedelta(hours=8),
        )
        add_stock(db, tenant, plant, material, on_hand=Decimal("20"), daily=Decimal("10"))
        add_event(
            db,
            tenant,
            event_type=OperationalEventType.SHIPMENT_ETA_CHANGED,
            event_category=OperationalEventCategory.SHIPMENT,
            plant_reference=plant.code,
            material_reference=material.code,
            shipment_reference=shipment.shipment_id,
            previous_value={"current_eta": (NOW + timedelta(days=1)).isoformat()},
            new_value={"current_eta": (NOW + timedelta(days=4)).isoformat()},
        )
        db.commit()

        workspace = get_risk_workspace(
            db,
            context_for(tenant),
            shipment_reference=shipment.shipment_id,
            severity="critical",
            now=NOW,
        )

        assert workspace.empty is False
        assert workspace.selected_risk is not None
        assert workspace.selected_risk.risk_type == "inbound_delay_against_cover"
        assert workspace.exposure is not None
        assert workspace.exposure.exposure_basis == "inbound_delay_against_cover"
        assert workspace.exposure.exposure_level == "immediate"
        assert "inbound_delay_against_cover" in workspace.exposure.related_risk_types
        assert workspace.shipment_continuity[0].status == "degraded"
        assert workspace.timeline.total == 1
        assert workspace.context_graph is not None
        assert_graph_edges_have_nodes(workspace.context_graph)


def test_demo_scenario_visibility_degradation_surfaces_trust_risks() -> None:
    with demo_session() as (db, tenant):
        plant, material = add_context(db, tenant, "VIS", "ORE")
        add_event(
            db,
            tenant,
            plant_reference=plant.code,
            material_reference=material.code,
            source_type=OperationalEventSourceType.AIS,
            confidence_score=Decimal("25"),
            freshness_status=OperationalEventFreshnessStatus.CRITICAL,
        )
        db.commit()

        workspace = get_risk_workspace(
            db,
            context_for(tenant),
            risk_type="stale_signal_risk",
            plant_reference=plant.code,
            material_reference=material.code,
            now=NOW,
        )

        assert workspace.empty is False
        assert workspace.selected_risk is not None
        assert workspace.selected_risk.risk_type == "stale_signal_risk"
        assert workspace.selected_risk.severity == "high"
        assert workspace.explainability is not None
        assert workspace.explainability.trust_context.trust_warnings
        assert workspace.exposure is not None
        assert workspace.exposure.exposure_basis == "stale_visibility"
        assert workspace.exposure.exposure_level == "watch"
        assert workspace.trust_summary is not None
        assert workspace.trust_summary.lowest_confidence_score == Decimal("25.00")
        assert workspace.trust_summary.worst_freshness_status == "critical"
        assert workspace.timeline.total == 1
        assert workspace.context_graph is not None
        assert_graph_edges_have_nodes(workspace.context_graph)


def test_demo_scenario_missing_operational_context_is_coherent() -> None:
    with demo_session() as (db, tenant):
        add_event(
            db,
            tenant,
            event_type=OperationalEventType.SHIPMENT_MILESTONE_UPDATED,
            event_category=OperationalEventCategory.SHIPMENT,
            plant_reference=None,
            material_reference=None,
            shipment_reference="SHIP-UNLINKED",
            new_value={"current_milestone": "in_transit"},
        )
        db.commit()

        workspace = get_risk_workspace(
            db,
            context_for(tenant),
            risk_type="missing_operational_context",
            shipment_reference="SHIP-UNLINKED",
            now=NOW,
        )

        assert workspace.empty is False
        assert workspace.selected_risk is not None
        assert workspace.selected_risk.risk_type == "missing_operational_context"
        assert workspace.explainability is not None
        assert workspace.explainability.primary_driver == "missing_operational_context"
        assert workspace.timeline.total == 1
        assert workspace.context_graph is not None
        assert_graph_edges_have_nodes(workspace.context_graph)
        node_ids = {node.id for node in workspace.context_graph.nodes}
        assert "shipment:SHIP-UNLINKED" in node_ids
        assert workspace.model_dump(mode="json")


def test_demo_scenario_outputs_are_deterministic_for_fixed_time() -> None:
    with demo_session() as (db, tenant):
        plant, material = add_context(db, tenant, "DET", "MAT")
        add_stock(db, tenant, plant, material, on_hand=Decimal("20"), daily=Decimal("10"))
        add_event(db, tenant, plant_reference=plant.code, material_reference=material.code)
        db.commit()

        first = get_risk_workspace(
            db,
            context_for(tenant),
            plant_reference=plant.code,
            material_reference=material.code,
            now=NOW,
        ).model_dump(mode="json")
        second = get_risk_workspace(
            db,
            context_for(tenant),
            plant_reference=plant.code,
            material_reference=material.code,
            now=NOW,
        ).model_dump(mode="json")

        assert first == second


class demo_session:
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
        tenant = Tenant(name="Demo Tenant", slug="demo-tenant")
        self.db.add(tenant)
        self.db.flush()
        return self.db, tenant

    def __exit__(self, exc_type, exc_value, traceback):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)


def add_context(
    db: Session,
    tenant: Tenant,
    plant_code: str,
    material_code: str,
) -> tuple[Plant, Material]:
    plant = Plant(tenant_id=tenant.id, code=plant_code, name=f"{plant_code} Plant", location=None)
    material = Material(
        tenant_id=tenant.id,
        code=material_code,
        name=f"{material_code} Material",
        category="raw",
        uom="MT",
    )
    db.add_all([plant, material])
    db.flush()
    return plant, material


def add_stock(
    db: Session,
    tenant: Tenant,
    plant: Plant,
    material: Material,
    *,
    on_hand: Decimal,
    daily: Decimal,
) -> None:
    db.add(
        StockSnapshot(
            tenant_id=tenant.id,
            plant_id=plant.id,
            material_id=material.id,
            on_hand_mt=on_hand,
            quality_held_mt=Decimal("0"),
            available_to_consume_mt=on_hand,
            daily_consumption_mt=daily,
            snapshot_time=NOW,
        )
    )


def add_shipment(
    db: Session,
    tenant: Tenant,
    plant: Plant,
    material: Material,
    *,
    shipment_id: str,
    current_eta: datetime,
    planned_eta: datetime,
    tracking_updated_at: datetime,
) -> Shipment:
    shipment = Shipment(
        tenant_id=tenant.id,
        shipment_id=shipment_id,
        material_id=material.id,
        plant_id=plant.id,
        supplier_name="Demo Supplier",
        quantity_mt=Decimal("50"),
        vessel_name="MV Demo",
        imo_number="1234567",
        mmsi="987654321",
        planned_eta=planned_eta,
        current_eta=current_eta,
        latest_eta=planned_eta,
        current_milestone="in_transit",
        last_tracking_update_at=tracking_updated_at,
        current_state=ShipmentState.IN_TRANSIT,
        source_of_truth="manual_upload",
        latest_update_at=tracking_updated_at,
    )
    db.add(shipment)
    db.flush()
    return shipment


def add_event(
    db: Session,
    tenant: Tenant,
    *,
    event_type: OperationalEventType = OperationalEventType.INVENTORY_STOCK_UPDATED,
    event_category: OperationalEventCategory = OperationalEventCategory.INVENTORY,
    source_type: OperationalEventSourceType = OperationalEventSourceType.FILE_INGESTION,
    plant_reference: str | None,
    material_reference: str | None,
    shipment_reference: str | None = None,
    confidence_score: Decimal | None = None,
    freshness_status: OperationalEventFreshnessStatus | None = None,
    previous_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    create_operational_event(
        db,
        OperationalEventCreate(
            tenant_id=tenant.id,
            event_type=event_type,
            event_category=event_category,
            source_type=source_type,
            source_reference=source_type.value,
            occurred_at=NOW - timedelta(days=5)
            if freshness_status == OperationalEventFreshnessStatus.CRITICAL
            else NOW,
            detected_at=NOW,
            plant_reference=plant_reference,
            material_reference=material_reference,
            shipment_reference=shipment_reference,
            quantity_value=(
                Decimal("20") if event_category == OperationalEventCategory.INVENTORY else None
            ),
            quantity_unit="MT" if event_category == OperationalEventCategory.INVENTORY else None,
            previous_value=previous_value,
            new_value=new_value or {"available_to_consume_mt": "20"},
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


def assert_graph_edges_have_nodes(graph) -> None:
    node_ids = {node.id for node in graph.nodes}
    assert graph.nodes
    assert all(edge.from_node_id in node_ids for edge in graph.edges)
    assert all(edge.to_node_id in node_ids for edge in graph.edges)
