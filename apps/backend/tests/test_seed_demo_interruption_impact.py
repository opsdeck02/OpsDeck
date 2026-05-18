from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Tenant
from app.modules.stock.service import calculate_stock_cover_summary
from app.schemas.context import RequestContext
from scripts import seed_demo


def test_seeded_demo_has_one_calculated_interruption_impact(monkeypatch, capsys) -> None:
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
            summary = calculate_stock_cover_summary(
                db,
                RequestContext(
                    tenant_id=tenant.id,
                    tenant_slug=tenant.slug,
                    role="logistics_user",
                    user_id=1,
                ),
            )
            configured = stock_row(summary.rows, "JAM", "COKING_COAL")
            unconfigured = stock_row(summary.rows, "KAL", "LIMESTONE")

            configured_impact = configured.calculation.operational_interruption_impact
            assert configured_impact is not None
            assert configured_impact.calculation_status == "calculated"
            assert configured_impact.currency == "INR"
            assert configured_impact.final_estimated_impact is not None
            assert (
                configured_impact.material_exposure_value
                == configured.calculation.estimated_value_at_risk
            )

            unconfigured_impact = unconfigured.calculation.operational_interruption_impact
            assert unconfigured_impact is not None
            assert unconfigured_impact.calculation_status == "insufficient_config"
            assert unconfigured_impact.operational_interruption_impact is None
    finally:
        Base.metadata.drop_all(bind=engine)


def stock_row(rows, plant_code: str, material_code: str):
    return next(
        row for row in rows if row.plant_code == plant_code and row.material_code == material_code
    )
