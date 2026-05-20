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
    Plant,
    Role,
    Shipment,
    ShipmentInboundTrustConfig,
    Supplier,
    Tenant,
    TenantMembership,
    User,
)
from app.models.enums import ShipmentState
from app.modules.auth.constants import TENANT_ADMIN
from app.modules.auth.security import hash_password
from app.modules.rules.inbound_delay_cover import evaluate_inbound_delay_cover_intelligence
from app.modules.shipments.continuity import calculate_shipment_continuity
from app.modules.shipments.visibility_confidence import calculate_visibility_confidence
from app.modules.stock.continuity import calculate_inventory_continuity

NOW = datetime(2026, 5, 20, 12, tzinfo=UTC)


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
        seed_admin_data(db)

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


def test_create_and_update_shipment_inbound_trust_config(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_id, material_id = context_ids("tenant-a")
    headers = auth_headers(client, "admin-a@test.local", "tenant-a")

    created = client.put(
        "/api/v1/impact/shipment-inbound-trust",
        headers=headers,
        json=payload(plant_id, material_id, profile="ocean", cadence="72"),
    )
    updated = client.put(
        "/api/v1/impact/shipment-inbound-trust",
        headers=headers,
        json=payload(plant_id, material_id, profile="inland", cadence="6"),
    )
    fetched = client.get(
        f"/api/v1/impact/shipment-inbound-trust?plant_id={plant_id}&material_id={material_id}",
        headers=headers,
    )

    assert created.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["id"] == created.json()["id"]
    assert fetched.status_code == 200
    assert fetched.json()["visibility_profile"] == "inland"
    assert fetched.json()["expected_visibility_cadence_hours"] == "6.00"


def test_shipment_inbound_trust_tenant_isolation(
    client_and_session: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _ = client_and_session
    plant_b_id, material_b_id = context_ids("tenant-b")

    response = client.put(
        "/api/v1/impact/shipment-inbound-trust",
        headers=auth_headers(client, "admin-a@test.local", "tenant-a"),
        json=payload(plant_b_id, material_b_id),
    )

    assert response.status_code == 404


def test_config_overrides_visibility_cadence_and_eta_tolerance() -> None:
    config = trust_config(
        visibility_profile="ocean",
        expected_visibility_cadence_hours=Decimal("120"),
        eta_drift_tolerance_hours=Decimal("48"),
    )
    result = calculate_visibility_confidence(
        shipment(
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
            planned_eta=NOW + timedelta(days=2),
            current_eta=NOW + timedelta(days=2, hours=36),
            latest_update_at=NOW - timedelta(hours=96),
        ),
        now=NOW,
        trust_config=config,
    )

    assert result.visibility_profile == "ocean"
    assert result.expected_visibility_cadence_hours == Decimal("120")
    assert result.eta_drift_tolerance_hours == Decimal("48")
    assert result.eta_behavior_status == "stable"
    assert any("Configured ETA drift tolerance is 48" in reason for reason in result.reason_chain)


def test_missing_config_preserves_visibility_defaults() -> None:
    result = calculate_visibility_confidence(
        shipment(
            current_state=ShipmentState.INLAND_TRANSIT,
            current_milestone="truck dispatched",
        ),
        now=NOW,
    )

    assert result.visibility_profile == "inland"
    assert result.expected_visibility_cadence_hours == Decimal("6")
    assert result.eta_drift_tolerance_hours == Decimal("4")


def test_weak_visibility_threshold_changes_trusted_protection_weakness() -> None:
    with managed_session() as db:
        ctx = seed_operational_context(db)
        db.add(
            trust_config(
                tenant_id=ctx.tenant.id,
                plant_id=ctx.plant.id,
                material_id=ctx.material.id,
                weak_visibility_threshold=Decimal("0.80"),
            )
        )
        db.commit()
        shipment_model = shipment(ctx)

        result = evaluate_inbound_delay_cover_intelligence(
            shipment_continuity(shipment_model),
            inventory(days_of_cover=Decimal("10"), trusted_ratio=Decimal("0.70")),
            db=db,
            tenant_id=ctx.tenant.id,
            shipment=shipment_model,
            now=NOW,
        )

        assert result.trusted_protection_weak is True
        assert any("Configured weak visibility threshold used: 0.8000" in reason for reason in result.reason_chain)


def test_minimum_trusted_inbound_ratio_affects_inbound_delay_concern() -> None:
    with managed_session() as db:
        ctx = seed_operational_context(db)
        db.add(
            trust_config(
                tenant_id=ctx.tenant.id,
                plant_id=ctx.plant.id,
                material_id=ctx.material.id,
                weak_visibility_threshold=Decimal("0.35"),
                minimum_trusted_inbound_ratio=Decimal("0.80"),
            )
        )
        db.commit()
        shipment_model = shipment(ctx)

        result = evaluate_inbound_delay_cover_intelligence(
            shipment_continuity(shipment_model),
            inventory(days_of_cover=Decimal("10"), trusted_ratio=Decimal("0.70")),
            db=db,
            tenant_id=ctx.tenant.id,
            shipment=shipment_model,
            now=NOW,
        )

        assert result.trusted_protection_weak is True
        assert any("Configured minimum trusted inbound ratio used: 0.8000" in reason for reason in result.reason_chain)


def test_unverified_inbound_handling_preserves_physical_quantity() -> None:
    config = trust_config(
        weak_visibility_threshold=Decimal("0.35"),
        allow_unverified_inbound_protection=False,
    )
    result = calculate_visibility_confidence(
        shipment(current_eta=None, latest_update_at=None),
        now=NOW,
        trust_config=config,
    )

    assert result.physical_inbound_quantity_mt == Decimal("100.00")
    assert result.trusted_inbound_protection_mt == Decimal("35.00")
    assert result.visibility_uncertain_quantity_mt == Decimal("65.00")
    assert any("physical inbound quantity remains unchanged" in reason for reason in result.reason_chain)


class OperationalContext:
    def __init__(self, tenant: Tenant, plant: Plant, material: Material, supplier: Supplier):
        self.tenant = tenant
        self.plant = plant
        self.material = material
        self.supplier = supplier


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


def seed_admin_data(db: Session) -> None:
    role = Role(name=TENANT_ADMIN, description="Tenant admin")
    tenant_a = Tenant(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant(name="Tenant B", slug="tenant-b")
    db.add_all([role, tenant_a, tenant_b])
    db.flush()
    for tenant, suffix in ((tenant_a, "a"), (tenant_b, "b")):
        user = User(
            email=f"admin-{suffix}@test.local",
            full_name=f"Admin {suffix.upper()}",
            password_hash=hash_password("Password123!"),
            is_active=True,
        )
        plant = Plant(tenant_id=tenant.id, code=f"P{suffix.upper()}", name=f"Plant {suffix.upper()}", location="India")
        material = Material(tenant_id=tenant.id, code=f"M{suffix.upper()}", name=f"Material {suffix.upper()}", category="raw", uom="MT")
        db.add_all([user, plant, material])
        db.flush()
        db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role_id=role.id, is_active=True))
    db.commit()


def seed_operational_context(db: Session) -> OperationalContext:
    tenant = Tenant(name="Tenant", slug="tenant")
    db.add(tenant)
    db.flush()
    plant = Plant(tenant_id=tenant.id, code="P1", name="Plant 1", location="IN")
    material = Material(tenant_id=tenant.id, code="M1", name="Material 1", category="raw", uom="MT")
    supplier = Supplier(tenant_id=tenant.id, name="Supplier 1", code="SUP1")
    db.add_all([plant, material, supplier])
    db.flush()
    return OperationalContext(tenant, plant, material, supplier)


def auth_headers(client: TestClient, email: str, tenant_slug: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Tenant-Slug": tenant_slug}


def context_ids(tenant_slug: str) -> tuple[int, int]:
    with next(app.dependency_overrides[get_db]()) as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
        assert tenant is not None
        plant = db.scalar(select(Plant).where(Plant.tenant_id == tenant.id))
        material = db.scalar(select(Material).where(Material.tenant_id == tenant.id))
        assert plant is not None
        assert material is not None
        return plant.id, material.id


def payload(
    plant_id: int,
    material_id: int,
    *,
    profile: str = "mixed",
    cadence: str = "24",
) -> dict[str, object]:
    return {
        "plant_id": plant_id,
        "material_id": material_id,
        "visibility_profile": profile,
        "expected_visibility_cadence_hours": cadence,
        "eta_drift_tolerance_hours": "12",
        "weak_visibility_threshold": "0.50",
        "minimum_trusted_inbound_ratio": None,
        "allow_unverified_inbound_protection": False,
        "is_active": True,
    }


def trust_config(**overrides) -> ShipmentInboundTrustConfig:
    values = {
        "tenant_id": 1,
        "plant_id": 1,
        "material_id": 1,
        "visibility_profile": "mixed",
        "expected_visibility_cadence_hours": Decimal("24"),
        "eta_drift_tolerance_hours": Decimal("12"),
        "weak_visibility_threshold": Decimal("0.50"),
        "minimum_trusted_inbound_ratio": None,
        "allow_unverified_inbound_protection": False,
        "is_active": True,
    }
    values.update(overrides)
    return ShipmentInboundTrustConfig(**values)


def shipment(ctx: OperationalContext | None = None, **overrides) -> Shipment:
    values = {
        "tenant_id": ctx.tenant.id if ctx else 1,
        "shipment_id": "SHIP-1",
        "plant_id": ctx.plant.id if ctx else 1,
        "material_id": ctx.material.id if ctx else 1,
        "supplier_id": ctx.supplier.id if ctx else None,
        "supplier_name": ctx.supplier.name if ctx else "Supplier",
        "quantity_mt": Decimal("100"),
        "planned_eta": NOW + timedelta(days=2),
        "current_eta": NOW + timedelta(days=2),
        "latest_eta": None,
        "current_state": ShipmentState.IN_TRANSIT,
        "current_milestone": "in_transit",
        "source_of_truth": "manual_upload",
        "latest_update_at": NOW - timedelta(hours=2),
    }
    values.update(overrides)
    return Shipment(**values)


def shipment_continuity(shipment_model: Shipment):
    return calculate_shipment_continuity(
        shipment_reference=shipment_model.shipment_id,
        eta=shipment_model.current_eta,
        previous_eta=shipment_model.latest_eta,
        planned_eta=shipment_model.planned_eta,
        current_milestone=shipment_model.current_milestone,
        tracking_updated_at=shipment_model.latest_update_at,
        linked_purchase_order_reference="PO-1",
        linked_material_reference="M1",
        linked_plant_reference="P1",
        current_state=shipment_model.current_state,
        now=NOW,
    )


def inventory(*, days_of_cover: Decimal, trusted_ratio: Decimal):
    physical = Decimal("100")
    trusted = (physical * trusted_ratio).quantize(Decimal("0.01"))
    uncertain = physical - trusted
    return calculate_inventory_continuity(
        plant_reference="P1",
        material_reference="M1",
        on_hand_quantity=days_of_cover * Decimal("10"),
        daily_consumption_rate=Decimal("10"),
        inbound_committed_quantity=physical,
        trusted_inbound_quantity=trusted,
        uncertain_inbound_quantity=uncertain,
        physical_inbound_quantity_mt=physical,
        trusted_inbound_protection_mt=trusted,
        visibility_uncertain_quantity_mt=uncertain,
        unit="MT",
        now=NOW,
    )
