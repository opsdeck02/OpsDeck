from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Material, Plant, Shipment, StockSnapshot, Tenant
from app.models.enums import ShipmentState
from app.modules.signal_engine.service import get_risk_workspace
from app.schemas.context import RequestContext

NOW = datetime(2026, 5, 22, 9, tzinfo=UTC)


def test_single_inbound_returns_strong_protection_metadata() -> None:
    with managed_session() as db:
        ctx = seed_context(db)
        add_stock(db, ctx)
        add_shipment(db, ctx, shipment_id="SHIP-STRONG", current_eta=NOW + timedelta(days=1))
        db.commit()

        workspace = get_risk_workspace(
            db,
            request_context(ctx.tenant),
            risk_type="days_of_cover_breach",
            now=NOW,
        )

        shipment = only_shipment(workspace)
        assert shipment.physical_quantity == Decimal("100.00")
        assert shipment.trusted_quantity is not None
        assert shipment.protective_quantity == shipment.trusted_quantity
        assert shipment.protective_value_label == "Strong protection"
        assert shipment.trust_level == "strong"
        assert shipment.is_currently_protective is True
        assert "strong protection" in (shipment.protection_explanation or "")


def test_multiple_inbound_rows_get_distinct_protection_values() -> None:
    with managed_session() as db:
        ctx = seed_context(db)
        add_stock(db, ctx)
        add_shipment(db, ctx, shipment_id="SHIP-STRONG", current_eta=NOW + timedelta(days=1))
        add_shipment(
            db,
            ctx,
            shipment_id="SHIP-WEAK",
            current_eta=NOW + timedelta(days=4),
            planned_eta=NOW + timedelta(days=1),
            latest_update_at=NOW - timedelta(hours=24),
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck delayed exception",
        )
        db.commit()

        workspace = get_risk_workspace(
            db,
            request_context(ctx.tenant),
            risk_type="days_of_cover_breach",
            now=NOW,
        )
        shipments = {item.shipment_reference: item for item in workspace.shipment_continuity}

        assert shipments["SHIP-STRONG"].protective_value_label == "Strong protection"
        assert shipments["SHIP-WEAK"].protective_value_label == "Weak protection"
        assert shipments["SHIP-STRONG"].trusted_quantity != shipments["SHIP-WEAK"].trusted_quantity
        assert shipments["SHIP-WEAK"].trusted_quantity < shipments["SHIP-WEAK"].physical_quantity


def test_stale_inbound_is_marked_weak() -> None:
    with managed_session() as db:
        ctx = seed_context(db)
        add_stock(db, ctx)
        add_shipment(
            db,
            ctx,
            shipment_id="SHIP-STALE",
            current_eta=NOW + timedelta(days=2),
            latest_update_at=NOW - timedelta(hours=30),
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
        )
        db.commit()

        workspace = get_risk_workspace(
            db,
            request_context(ctx.tenant),
            risk_type="days_of_cover_breach",
            now=NOW,
        )

        shipment = only_shipment(workspace)
        assert shipment.protective_value_label == "Weak protection"
        assert shipment.trust_level == "weak"
        assert (
            "degraded" in (shipment.trust_reason or "").lower()
            or shipment.trusted_quantity < shipment.physical_quantity
        )


def test_inbound_after_projected_exhaustion_is_not_currently_protective() -> None:
    with managed_session() as db:
        ctx = seed_context(db)
        add_stock(db, ctx)
        add_shipment(db, ctx, shipment_id="SHIP-LATE", current_eta=NOW + timedelta(days=20))
        db.commit()

        workspace = get_risk_workspace(
            db,
            request_context(ctx.tenant),
            risk_type="days_of_cover_breach",
            now=NOW,
        )

        shipment = only_shipment(workspace)
        assert shipment.protective_value_label == "Not currently protective"
        assert shipment.is_currently_protective is False
        assert shipment.protective_quantity == Decimal("0.00")
        assert "after projected cover loss" in (shipment.protection_explanation or "")


def test_missing_inbound_data_returns_unknown_protection_with_explanation() -> None:
    with managed_session() as db:
        ctx = seed_context(db)
        shipment_model = Shipment(
            tenant_id=ctx.tenant.id,
            shipment_id="SHIP-UNKNOWN",
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            supplier_name="Supplier",
            quantity_mt=Decimal("100"),
            planned_eta=NOW + timedelta(days=1),
            current_eta=None,
            current_state=ShipmentState.IN_TRANSIT,
            current_milestone="in_transit",
            source_of_truth="manual_upload",
            latest_update_at=NOW - timedelta(hours=2),
            last_tracking_update_at=NOW - timedelta(hours=2),
        )
        from app.modules.shipments.continuity import calculate_shipment_continuity
        from app.modules.signal_engine.service import enrich_shipment_protection

        continuity = calculate_shipment_continuity(
            shipment_reference=shipment_model.shipment_id,
            eta=None,
            planned_eta=shipment_model.planned_eta,
            current_milestone=shipment_model.current_milestone,
            tracking_updated_at=shipment_model.last_tracking_update_at,
            linked_purchase_order_reference="PO-1",
            linked_material_reference=ctx.material.code,
            linked_plant_reference=ctx.plant.code,
            current_state=shipment_model.current_state,
            now=NOW,
        )
        shipment = enrich_shipment_protection(
            db,
            request_context(ctx.tenant),
            shipment_model,
            continuity,
            inventory=None,
            now=NOW,
        )

        assert shipment.physical_quantity == Decimal("100.00")
        assert shipment.trusted_quantity is not None
        assert shipment.protective_value_label == "Unknown protection"
        assert shipment.trust_level == "unknown"
        assert shipment.is_currently_protective is None
        assert "Current ETA is missing" in (shipment.protection_explanation or "")


def test_existing_workspace_response_keeps_legacy_shipment_fields() -> None:
    with managed_session() as db:
        ctx = seed_context(db)
        add_stock(db, ctx)
        add_shipment(db, ctx, shipment_id="SHIP-STRONG", current_eta=NOW + timedelta(days=1))
        db.commit()

        workspace = get_risk_workspace(
            db,
            request_context(ctx.tenant),
            risk_type="days_of_cover_breach",
            now=NOW,
        )
        dumped = workspace.model_dump(mode="json")
        shipment = dumped["shipment_continuity"][0]

        assert shipment["shipment_reference"] == "SHIP-STRONG"
        assert shipment["status"] in {"on_track", "watch"}
        assert shipment["tracking_freshness_status"] in {"fresh", "delayed"}
        assert shipment["protective_value_label"] == "Strong protection"


class Context:
    def __init__(self, tenant: Tenant, plant: Plant, material: Material):
        self.tenant = tenant
        self.plant = plant
        self.material = material


def managed_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    class ManagedSession:
        def __enter__(self) -> Session:
            self.db = SessionLocal()
            return self.db

        def __exit__(self, exc_type, exc, tb) -> None:
            self.db.close()
            Base.metadata.drop_all(bind=engine)

    return ManagedSession()


def seed_context(db: Session) -> Context:
    tenant = Tenant(name="Pilot Tenant", slug="pilot-tenant")
    db.add(tenant)
    db.flush()
    plant = Plant(tenant_id=tenant.id, code="P1", name="Plant 1", location="IN")
    material = Material(tenant_id=tenant.id, code="COAL", name="Coking Coal", category="raw")
    db.add_all([plant, material])
    db.flush()
    return Context(tenant, plant, material)


def add_stock(db: Session, ctx: Context) -> None:
    db.add(
        StockSnapshot(
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            on_hand_mt=Decimal("20"),
            quality_held_mt=Decimal("0"),
            available_to_consume_mt=Decimal("20"),
            daily_consumption_mt=Decimal("10"),
            snapshot_time=NOW,
        )
    )


def add_shipment(
    db: Session,
    ctx: Context,
    *,
    shipment_id: str,
    current_eta: datetime | None,
    planned_eta: datetime | None = None,
    latest_update_at: datetime | None = None,
    current_state: ShipmentState = ShipmentState.IN_TRANSIT,
    current_milestone: str = "in_transit",
) -> None:
    db.add(
        Shipment(
            tenant_id=ctx.tenant.id,
            shipment_id=shipment_id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            supplier_name="Supplier",
            quantity_mt=Decimal("100"),
            vessel_name="MV Pilot",
            planned_eta=planned_eta or NOW + timedelta(days=1),
            current_eta=current_eta,
            current_state=current_state,
            current_milestone=current_milestone,
            source_of_truth="manual_upload",
            latest_update_at=latest_update_at or NOW - timedelta(hours=2),
            last_tracking_update_at=latest_update_at or NOW - timedelta(hours=2),
        )
    )


def request_context(tenant: Tenant) -> RequestContext:
    return RequestContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        role="tenant_admin",
        user_id=1,
    )


def only_shipment(workspace):
    assert len(workspace.shipment_continuity) == 1
    return workspace.shipment_continuity[0]
