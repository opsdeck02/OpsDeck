from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Material, Plant, Shipment, Tenant
from app.modules.impact.configuration_validation import validate_operational_configuration
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
