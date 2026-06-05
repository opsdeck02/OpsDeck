from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import (
    LineStopIncident,
    Material,
    Plant,
    PlantMaterialThreshold,
    Role,
    StockSnapshot,
    Tenant,
    TenantMembership,
    User,
)
from app.modules.auth.constants import LOGISTICS_USER
from app.modules.auth.security import hash_password
from app.modules.line_stops.service import build_historical_validation_report
from app.schemas.context import RequestContext


def test_historical_validation_report_calculates_warning_lead_time() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            tenant = seed_historical_validation_data(db)
            report = build_historical_validation_report(
                db,
                RequestContext(
                    tenant_id=tenant.id,
                    tenant_slug=tenant.slug,
                    role="tenant_admin",
                    user_id=1,
                ),
            )

        assert report.total_incidents == 1
        assert report.incidents_with_warning == 1
        assert report.results[0].predicted_warning_date == datetime(2026, 6, 6, tzinfo=UTC)
        assert report.results[0].lead_time_gained_hours == Decimal("96.00")
        assert report.results[0].confidence_level == "high"
    finally:
        Base.metadata.drop_all(bind=engine)


def test_historical_validation_endpoint_returns_report() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            tenant = seed_historical_validation_data(db)
            seed_login_user(db, tenant)

        def override_get_db() -> Generator[Session, None, None]:
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"email": "planner@test.local", "password": "Password123!"},
            )
            token = login.json()["access_token"]
            response = client.get(
                "/api/v1/line-stops/historical-validation",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tenant-Slug": "tenant-a",
                },
            )

        assert response.status_code == 200
        assert response.json()["total_incidents"] == 1
        assert response.json()["results"][0]["lead_time_gained_hours"] == "96.00"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def seed_historical_validation_data(db: Session) -> Tenant:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    db.add(tenant)
    db.flush()
    plant = Plant(tenant_id=tenant.id, code="P1", name="Plant 1", location="India")
    material = Material(
        tenant_id=tenant.id,
        code="COKE",
        name="Coking coal",
        category="coal",
        uom="MT",
    )
    db.add_all([plant, material])
    db.flush()
    db.add_all(
        [
            StockSnapshot(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                on_hand_mt=Decimal("100"),
                quality_held_mt=Decimal("0"),
                available_to_consume_mt=Decimal("100"),
                daily_consumption_mt=Decimal("10"),
                snapshot_time=datetime(2026, 6, 1, tzinfo=UTC),
            ),
            PlantMaterialThreshold(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                threshold_days=Decimal("2"),
                warning_days=Decimal("5"),
                minimum_buffer_stock_days=Decimal("3"),
            ),
            LineStopIncident(
                tenant_id=tenant.id,
                plant_id=plant.id,
                material_id=material.id,
                stopped_at=datetime(2026, 6, 10, tzinfo=UTC),
                duration_hours=Decimal("8"),
            ),
        ]
    )
    db.commit()
    return tenant


def seed_login_user(db: Session, tenant: Tenant) -> None:
    role = Role(name=LOGISTICS_USER, description="Logistics")
    user = User(
        email="planner@test.local",
        full_name="Planner",
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    db.add_all([role, user])
    db.flush()
    db.add(
        TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            role_id=role.id,
            is_active=True,
        )
    )
    db.commit()
