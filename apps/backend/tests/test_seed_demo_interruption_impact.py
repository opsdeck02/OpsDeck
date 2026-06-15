from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import LineStopIncident, Material, Plant, Shipment, Tenant
from app.modules.impact.configuration_validation import validate_operational_configuration
from app.modules.line_stops.service import build_historical_validation_report
from app.modules.stock.service import calculate_stock_cover_detail
from app.schemas.context import RequestContext
from scripts import seed_demo


def test_seed_demo_keeps_only_current_demo_sources(monkeypatch, capsys) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(seed_demo, "SessionLocal", SessionLocal)
    try:
        seed_demo.seed()
        capsys.readouterr()

        with SessionLocal() as db:
            tenant = db.scalar(select(Tenant).where(Tenant.slug == "demo-steel"))
            assert tenant is not None
            assert tenant.is_demo_tenant is True
            assert (
                db.scalar(
                    select(Plant).where(
                        Plant.tenant_id == tenant.id,
                        Plant.code.in_(["JAM", "KAL"]),
                    )
                )
                is None
            )
            assert (
                db.scalar(
                    select(Material).where(
                        Material.tenant_id == tenant.id,
                        Material.code.in_(["COKING_COAL", "LIMESTONE"]),
                    )
                )
                is None
            )
            assert (
                db.scalar(
                    select(Shipment).where(
                        Shipment.tenant_id == tenant.id,
                        Shipment.shipment_id == "INB-PDP-COAL-117",
                    )
                )
                is None
            )
    finally:
        Base.metadata.drop_all(bind=engine)


def test_seed_demo_creates_ready_full_operational_config(monkeypatch, capsys) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(seed_demo, "SessionLocal", SessionLocal)
    try:
        seed_demo.seed()
        capsys.readouterr()

        with SessionLocal() as db:
            tenant = db.scalar(select(Tenant).where(Tenant.slug == "demo-steel"))
            assert tenant is not None
            plant = db.scalar(
                select(Plant).where(
                    Plant.tenant_id == tenant.id,
                    Plant.code == seed_demo.DEMO_PLANT_CODE,
                )
            )
            assert plant is not None
            materials = list(
                db.scalars(
                    select(Material).where(
                        Material.tenant_id == tenant.id,
                        Material.code.in_([config.code for config in seed_demo.DEMO_MATERIALS]),
                    )
                )
            )
            assert len(materials) == len(seed_demo.DEMO_MATERIALS)

            for material in materials:
                result = validate_operational_configuration(
                    db,
                    tenant_id=tenant.id,
                    plant_id=plant.id,
                    material_id=material.id,
                )
                assert result.validation_status == "ready"
                assert result.blocking_errors_count == 0
                assert result.readiness_score >= 85
    finally:
        Base.metadata.drop_all(bind=engine)


def test_seed_demo_creates_complete_coking_coal_pilot_story(monkeypatch, capsys) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(seed_demo, "SessionLocal", SessionLocal)
    try:
        seed_demo.seed()
        capsys.readouterr()

        with SessionLocal() as db:
            tenant = db.scalar(select(Tenant).where(Tenant.slug == "demo-steel"))
            assert tenant is not None
            plant = db.scalar(
                select(Plant).where(
                    Plant.tenant_id == tenant.id,
                    Plant.code == seed_demo.DEMO_PLANT_CODE,
                )
            )
            material = db.scalar(
                select(Material).where(
                    Material.tenant_id == tenant.id,
                    Material.code == "DEMO-COKING-COAL",
                )
            )
            assert plant is not None
            assert material is not None
            context = RequestContext(
                tenant_id=tenant.id,
                tenant_slug=tenant.slug,
                role="tenant_admin",
                user_id=1,
            )

            detail = calculate_stock_cover_detail(db, context, plant.id, material.id)
            assert detail is not None
            cover = detail.time_phased_cover
            assert cover is not None
            assert cover.warning_date is not None
            assert cover.reserve_breach_date is not None
            assert cover.critical_breach_date is not None
            assert cover.interruption_date is not None
            assert cover.current_projected_warning_date is not None
            assert cover.current_projected_reserve_breach_date is not None
            assert cover.current_projected_critical_breach_date is not None
            assert cover.current_projected_interruption_date is not None

            statuses = {
                item.shipment_id: item.protection_status
                for item in cover.shipment_evaluations
            }
            assert statuses["DEMO-COAL-PROTECTIVE-A"] == "PROTECTIVE"
            assert statuses["DEMO-COAL-LATE-B"] == "LATE_AFTER_RESERVE"
            assert statuses["DEMO-COAL-TOO-LATE-C"] == "TOO_LATE"
            late = next(
                item
                for item in cover.shipment_evaluations
                if item.shipment_id == "DEMO-COAL-TOO-LATE-C"
            )
            assert any("Supplier is not linked" in reason for reason in late.reasoning)
            assert "One or more inbound shipments are missing supplier master linkage." in (
                cover.assumptions_used
            )

            incident = db.scalar(
                select(LineStopIncident).where(
                    LineStopIncident.tenant_id == tenant.id,
                    LineStopIncident.plant_id == plant.id,
                    LineStopIncident.material_id == material.id,
                )
            )
            assert incident is not None
            report = build_historical_validation_report(db, context)
            assert report.total_incidents >= 1
            coking_result = next(
                result
                for result in report.results
                if result.material_id == material.id and result.plant_id == plant.id
            )
            assert coking_result.predicted_warning_date is not None
            assert coking_result.lead_time_gained_hours is not None
            assert coking_result.opsdeck_detection_result == "DETECTED"
            assert coking_result.confidence_classification == "HIGH CONFIDENCE"
            assert coking_result.warning_lead_time_days == Decimal("5.00")
            assert report.summary is not None
            assert report.summary.incidents_analyzed == 1
            assert report.summary.detected == 1
            assert report.summary.partially_detected == 0
            assert report.summary.missed == 0
            assert report.summary.detection_rate_percent == Decimal("100.00")
            assert report.summary.average_warning_lead_time_days == Decimal("5.00")
            assert "Days of Cover Breach" in coking_result.detection_signals
            assert "Inbound Delay Against Cover" in coking_result.detection_signals
            assert "Shipment Degraded" in coking_result.detection_signals
            assert "Trusted Inbound Reduction" in coking_result.detection_signals
            assert "Verify inbound shipment status" in coking_result.recommended_actions_replay
            assert "Escalate supplier" in coking_result.recommended_actions_replay
            assert "Review reserve stock" in coking_result.recommended_actions_replay
            assert "Activate contingency sourcing" in coking_result.recommended_actions_replay
            assert "Operational impact: Blast Furnace Production Exposure." in (
                incident.notes or ""
            )
    finally:
        Base.metadata.drop_all(bind=engine)
