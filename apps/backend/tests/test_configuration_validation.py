from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import (
    Material,
    MaterialProcessDependency,
    Plant,
    PlantMaterialThreshold,
    ProcessProductDependency,
    ProductionInterruptionImpactConfig,
    ProductionLine,
    Role,
    Shipment,
    ShipmentInboundTrustConfig,
    StockSnapshot,
    Supplier,
    Tenant,
    TenantMembership,
    User,
)
from app.models.enums import ShipmentState
from app.modules.auth.constants import TENANT_ADMIN
from app.modules.auth.security import hash_password
from app.modules.impact.configuration_validation import (
    clamp_score,
    validate_operational_configuration,
)

NOW = datetime(2026, 5, 21, 10, tzinfo=UTC)


@pytest.fixture()
def client_and_session() -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session() as db:
        seed_base(db)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), testing_session
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def test_fully_configured_context_returns_ready_high_score(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    _, SessionLocal = client_and_session
    with SessionLocal() as db:
        ctx = context(db, "tenant-a")
        configure_ready(db, ctx)

        result = validate_operational_configuration(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            now=NOW,
        )

        assert result.validation_status == "ready"
        assert result.readiness_score >= Decimal("85")
        assert result.blocking_errors_count == 0


def test_missing_thresholds_creates_warning(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    _, SessionLocal = client_and_session
    with SessionLocal() as db:
        ctx = context(db, "tenant-a")
        configure_ready(db, ctx, thresholds=False)

        result = validate_operational_configuration(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            now=NOW,
        )

        assert has_finding(result, "missing_continuity_thresholds", "warning")


def test_warning_days_less_than_threshold_days_returns_invalid(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    _, SessionLocal = client_and_session
    with SessionLocal() as db:
        ctx = context(db, "tenant-a")
        configure_ready(db, ctx)
        threshold = db.scalar(select(PlantMaterialThreshold).where(PlantMaterialThreshold.tenant_id == ctx.tenant.id))
        assert threshold is not None
        threshold.warning_days = Decimal("3")
        threshold.threshold_days = Decimal("7")

        result = validate_operational_configuration(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            now=NOW,
        )

        assert result.validation_status == "invalid"
        assert has_finding(result, "warning_days_less_than_threshold_days", "error")


def test_missing_interruption_config_creates_warning(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    _, SessionLocal = client_and_session
    with SessionLocal() as db:
        ctx = context(db, "tenant-a")
        configure_ready(db, ctx, interruption=False)

        result = validate_operational_configuration(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            now=NOW,
        )

        assert has_finding(result, "missing_interruption_impact_config", "warning")


def test_dependency_without_product_mix_creates_warning(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    _, SessionLocal = client_and_session
    with SessionLocal() as db:
        ctx = context(db, "tenant-a")
        configure_ready(db, ctx, product_mix=False)

        result = validate_operational_configuration(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            now=NOW,
        )

        assert has_finding(result, "process_product_mix_missing", "warning")


def test_product_mix_total_above_threshold_creates_warning(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    _, SessionLocal = client_and_session
    with SessionLocal() as db:
        ctx = context(db, "tenant-a")
        configure_ready(db, ctx, product_mix=False)
        line = db.scalar(select(ProductionLine).where(ProductionLine.tenant_id == ctx.tenant.id))
        assert line is not None
        db.add_all(
            [
                product(ctx, line.id, "HRC", Decimal("0.70")),
                product(ctx, line.id, "Billet", Decimal("0.70")),
            ]
        )
        db.flush()

        result = validate_operational_configuration(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            now=NOW,
        )

        assert has_finding(result, "product_mix_share_total_high", "warning")


def test_unrealistic_shipment_trust_cadence_creates_warning(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    _, SessionLocal = client_and_session
    with SessionLocal() as db:
        ctx = context(db, "tenant-a")
        configure_ready(db, ctx)
        config = db.scalar(select(ShipmentInboundTrustConfig).where(ShipmentInboundTrustConfig.tenant_id == ctx.tenant.id))
        assert config is not None
        config.visibility_profile = "ocean"
        config.expected_visibility_cadence_hours = Decimal("6")

        result = validate_operational_configuration(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            now=NOW,
        )

        assert has_finding(result, "import_profile_cadence_too_strict", "warning")


def test_missing_eta_on_active_shipment_creates_warning(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    _, SessionLocal = client_and_session
    with SessionLocal() as db:
        ctx = context(db, "tenant-a")
        configure_ready(db, ctx)
        shipment = db.scalar(select(Shipment).where(Shipment.tenant_id == ctx.tenant.id))
        assert shipment is not None
        shipment.current_eta = None

        result = validate_operational_configuration(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            now=NOW,
        )

        assert has_finding(result, "active_shipment_eta_missing", "warning")


def test_daily_consumption_non_positive_creates_error(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    _, SessionLocal = client_and_session
    with SessionLocal() as db:
        ctx = context(db, "tenant-a")
        configure_ready(db, ctx, stock=False)
        db.add(stock(ctx, daily_consumption=Decimal("0")))
        db.flush()

        result = validate_operational_configuration(
            db,
            tenant_id=ctx.tenant.id,
            plant_id=ctx.plant.id,
            material_id=ctx.material.id,
            now=NOW,
        )

        assert result.validation_status == "invalid"
        assert has_finding(result, "daily_consumption_non_positive", "error")


def test_readiness_score_clamps_at_zero() -> None:
    assert clamp_score(Decimal("-12")) == Decimal("0.00")
    assert clamp_score(Decimal("140")) == Decimal("100.00")


def test_endpoint_preserves_tenant_isolation(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, SessionLocal = client_and_session
    with SessionLocal() as db:
        ctx_b = context(db, "tenant-b")
        plant_id = ctx_b.plant.id
        material_id = ctx_b.material.id
    response = client.get(
        f"/api/v1/impact/configuration-validation?plant_id={plant_id}&material_id={material_id}",
        headers=auth_headers(client, "admin-a@test.local", "tenant-a"),
    )
    assert response.status_code == 404


def test_endpoint_returns_findings_cleanly(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, SessionLocal = client_and_session
    with SessionLocal() as db:
        ctx = context(db, "tenant-a")
        configure_ready(db, ctx, thresholds=False)
        plant_id = ctx.plant.id
        material_id = ctx.material.id

    response = client.get(
        f"/api/v1/impact/configuration-validation?plant_id={plant_id}&material_id={material_id}",
        headers=auth_headers(client, "admin-a@test.local", "tenant-a"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plant_id"] == plant_id
    assert body["material_id"] == material_id
    assert body["findings"]
    assert {"finding_code", "severity", "area", "title", "suggested_fix"}.issubset(
        body["findings"][0]
    )


class Context:
    def __init__(self, tenant: Tenant, plant: Plant, material: Material, supplier: Supplier):
        self.tenant = tenant
        self.plant = plant
        self.material = material
        self.supplier = supplier


def seed_base(db: Session) -> None:
    role = Role(name=TENANT_ADMIN, description="Tenant admin")
    db.add(role)
    db.flush()
    for suffix in ("a", "b"):
        tenant = Tenant(name=f"Tenant {suffix.upper()}", slug=f"tenant-{suffix}")
        user = User(
            email=f"admin-{suffix}@test.local",
            full_name=f"Admin {suffix.upper()}",
            password_hash=hash_password("TestOnlyCredential1!"),
            is_active=True,
        )
        db.add_all([tenant, user])
        db.flush()
        db.add(
            TenantMembership(
                tenant_id=tenant.id,
                user_id=user.id,
                role_id=role.id,
                is_active=True,
            )
        )
        db.add_all(
            [
                Plant(tenant_id=tenant.id, code=f"P{suffix}", name=f"Plant {suffix}", location="IN"),
                Material(tenant_id=tenant.id, code=f"M{suffix}", name=f"Material {suffix}", category="raw", uom="MT"),
                Supplier(tenant_id=tenant.id, code=f"S{suffix}", name=f"Supplier {suffix}"),
            ]
        )
    db.commit()


def context(db: Session, slug: str) -> Context:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
    assert tenant is not None
    plant = db.scalar(select(Plant).where(Plant.tenant_id == tenant.id))
    material = db.scalar(select(Material).where(Material.tenant_id == tenant.id))
    supplier = db.scalar(select(Supplier).where(Supplier.tenant_id == tenant.id))
    assert plant is not None and material is not None and supplier is not None
    return Context(tenant, plant, material, supplier)


def configure_ready(
    db: Session,
    ctx: Context,
    *,
    thresholds: bool = True,
    interruption: bool = True,
    product_mix: bool = True,
    trust: bool = True,
    stock: bool = True,
) -> None:
    if thresholds:
        db.add(
            PlantMaterialThreshold(
                tenant_id=ctx.tenant.id,
                plant_id=ctx.plant.id,
                material_id=ctx.material.id,
                warning_days=Decimal("14"),
                threshold_days=Decimal("7"),
                stockout_alert_horizon_days=Decimal("3"),
            )
        )
    if interruption:
        db.add(
            ProductionInterruptionImpactConfig(
                tenant_id=ctx.tenant.id,
                plant_id=ctx.plant.id,
                material_id=ctx.material.id,
                production_line_id=None,
                production_rate_mt_per_hour=Decimal("100"),
                finished_goods_value_per_mt=Decimal("70000"),
                survivable_hours_without_material=Decimal("4"),
                line_dependency_ratio=Decimal("0.90"),
                downtime_cost_per_hour=Decimal("100000"),
                restart_cost=Decimal("500000"),
                restart_time_hours=Decimal("2"),
                substitution_factor=Decimal("0.10"),
                cascading_impact_factor=Decimal("1.00"),
                currency="INR",
                is_active=True,
            )
        )
    line = ProductionLine(
        tenant_id=ctx.tenant.id,
        plant_id=ctx.plant.id,
        code="BF-1",
        name="Blast Furnace 1",
        is_active=True,
    )
    db.add(line)
    db.flush()
    db.add(
        MaterialProcessDependency(
            tenant_id=ctx.tenant.id,
            material_id=ctx.material.id,
            process_id=line.id,
            dependency_ratio=Decimal("0.90"),
            is_active=True,
        )
    )
    if product_mix:
        db.add(product(ctx, line.id, "HRC", Decimal("1.00")))
    if trust:
        db.add(
            ShipmentInboundTrustConfig(
                tenant_id=ctx.tenant.id,
                plant_id=ctx.plant.id,
                material_id=ctx.material.id,
                visibility_profile="ocean",
                expected_visibility_cadence_hours=Decimal("72"),
                eta_drift_tolerance_hours=Decimal("24"),
                weak_visibility_threshold=Decimal("0.50"),
                minimum_trusted_inbound_ratio=Decimal("0.50"),
                allow_unverified_inbound_protection=False,
                is_active=True,
            )
        )
    if stock:
        db.add(stock_snapshot := stock_model(ctx))
        assert stock_snapshot.daily_consumption_mt > 0
    for index in range(3):
        db.add(shipment_model(ctx, shipment_id=f"SHP-{index}"))
    db.commit()


def product(
    ctx: Context,
    line_id: int,
    product_name: str,
    output_share: Decimal,
) -> ProcessProductDependency:
    return ProcessProductDependency(
        tenant_id=ctx.tenant.id,
        process_id=line_id,
        product_name=product_name,
        output_share_ratio=output_share,
        product_value_per_mt=Decimal("72000"),
        operational_criticality_factor=Decimal("1.00"),
        is_active=True,
    )


def stock_model(
    ctx: Context,
    *,
    daily_consumption: Decimal = Decimal("10"),
    available: Decimal = Decimal("100"),
) -> StockSnapshot:
    return StockSnapshot(
        tenant_id=ctx.tenant.id,
        plant_id=ctx.plant.id,
        material_id=ctx.material.id,
        on_hand_mt=Decimal("100"),
        quality_held_mt=Decimal("0"),
        available_to_consume_mt=available,
        daily_consumption_mt=daily_consumption,
        snapshot_time=NOW,
    )


def stock(
    ctx: Context,
    *,
    daily_consumption: Decimal = Decimal("10"),
    available: Decimal = Decimal("100"),
) -> StockSnapshot:
    return stock_model(ctx, daily_consumption=daily_consumption, available=available)


def shipment_model(
    ctx: Context,
    *,
    shipment_id: str = "SHP",
    quantity: Decimal = Decimal("100"),
) -> Shipment:
    return Shipment(
        tenant_id=ctx.tenant.id,
        shipment_id=shipment_id,
        plant_id=ctx.plant.id,
        material_id=ctx.material.id,
        supplier_id=ctx.supplier.id,
        supplier_name=ctx.supplier.name,
        quantity_mt=quantity,
        vessel_name="MV Demo",
        imo_number="IMO1234567",
        mmsi="123456789",
        planned_eta=NOW + timedelta(days=3),
        current_eta=NOW + timedelta(days=3),
        current_state=ShipmentState.IN_TRANSIT,
        source_of_truth="manual_upload",
        latest_update_at=NOW,
        last_tracking_update_at=NOW,
    )


def auth_headers(client: TestClient, email: str, tenant_slug: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "TestOnlyCredential1!"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": tenant_slug}


def has_finding(result, code: str, severity: str) -> bool:
    return any(
        item.finding_code == code and item.severity == severity for item in result.findings
    )
