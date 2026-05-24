from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    ExceptionCase,
    ExceptionComment,
    ExternalDataSource,
    InlandMovement,
    LineStopIncident,
    OperationalEvent,
    Plant,
    PlantMaterialThreshold,
    PortEvent,
    ProductionInterruptionImpactConfig,
    Role,
    Shipment,
    ShipmentUpdate,
    StockSnapshot,
    Tenant,
    TenantMembership,
    User,
)
from app.modules.auth.constants import (
    BUYER_USER,
    LOGISTICS_USER,
    MANAGEMENT_USER,
    PLANNER_USER,
    ROLE_NAMES,
    SPONSOR_USER,
    TENANT_ADMIN,
)
from app.modules.auth.security import hash_password

ROLE_DESCRIPTIONS = {
    TENANT_ADMIN: "Tenant administrator with continuity intelligence access",
    BUYER_USER: "Buyer responsible for supplier continuity and inbound stability",
    LOGISTICS_USER: "Logistics operator responsible for inbound continuity signals",
    PLANNER_USER: "Planner responsible for available cover and ETA assumptions",
    MANAGEMENT_USER: "Management stakeholder with executive visibility",
    SPONSOR_USER: "Executive sponsor with read-only operational visibility",
}

DEMO_USERS = [
    ("admin@demo.opsdeck.local", "Demo Admin", TENANT_ADMIN),
    ("buyer@demo.opsdeck.local", "Demo Buyer", BUYER_USER),
    ("logistics@demo.opsdeck.local", "Demo Logistics", LOGISTICS_USER),
    ("planner@demo.opsdeck.local", "Demo Planner", PLANNER_USER),
    ("management@demo.opsdeck.local", "Demo Management", MANAGEMENT_USER),
    ("sponsor@demo.opsdeck.local", "Demo Sponsor", SPONSOR_USER),
]

LEGACY_PLANT_CODES = ("JAM", "KAL")
LEGACY_MATERIAL_CODES = (
    "COKING_COAL",
    "IRON_ORE_FINES",
    "PELLETS",
    "LIMESTONE",
    "DOLOMITE",
)
LEGACY_SHIPMENT_REFS = (
    "INB-PDP-COAL-117",
    "RAKE-BRB-ORE-042",
    "RAKE-DHM-LIME-014",
    "INB-HLD-DOLO-026",
    "INB-VZG-PELLET-022",
)
LEGACY_SUPPLIER_CODES = ("QCL", "OMC", "EFM", "VPOS")
LEGACY_SOURCE_NAMES = ("Demo ERP inbound feed", "Continuity inbound source feed")


def get_or_create_role(db: Session, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role:
        return role
    role = Role(name=name, description=ROLE_DESCRIPTIONS[name])
    db.add(role)
    db.flush()
    return role


def get_or_create_user(db: Session, email: str, full_name: str) -> User:
    legacy_email = email.replace("opsdeck.local", "steelops.local")
    user = db.scalar(select(User).where(User.email.in_([email, legacy_email])))
    if user:
        user.email = email
        user.full_name = full_name
        user.password_hash = hash_password("Password123!")
        user.is_active = True
        return user
    user = User(
        email=email,
        full_name=full_name,
        password_hash=hash_password("Password123!"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def get_or_create_superadmin(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == "superadmin@opsdeck.local"))
    if user is None:
        user = User(
            email="superadmin@opsdeck.local",
            full_name="OpsDeck Superadmin",
            password_hash=hash_password("SuperAdmin123!"),
            is_active=True,
            is_superadmin=True,
        )
        db.add(user)
        db.flush()
    else:
        user.password_hash = hash_password("SuperAdmin123!")
        user.is_active = True
        user.is_superadmin = True
    return user


def cleanup_legacy_demo_operational_data(db: Session, tenant_id: int) -> None:
    legacy_plants = select(Plant.id).where(
        Plant.tenant_id == tenant_id,
        Plant.code.in_(LEGACY_PLANT_CODES),
    )
    legacy_shipments = select(Shipment.id).where(
        Shipment.tenant_id == tenant_id,
        (Shipment.shipment_id.in_(LEGACY_SHIPMENT_REFS))
        | (Shipment.plant_id.in_(legacy_plants)),
    )

    db.execute(
        delete(ExceptionComment).where(
            ExceptionComment.tenant_id == tenant_id,
            ExceptionComment.exception_case_id.in_(
                select(ExceptionCase.id).where(ExceptionCase.tenant_id == tenant_id)
            ),
        )
    )
    db.execute(delete(ExceptionCase).where(ExceptionCase.tenant_id == tenant_id))
    db.execute(delete(LineStopIncident).where(LineStopIncident.tenant_id == tenant_id))
    db.execute(delete(PortEvent).where(PortEvent.tenant_id == tenant_id))
    db.execute(delete(InlandMovement).where(InlandMovement.tenant_id == tenant_id))
    db.execute(delete(ShipmentUpdate).where(ShipmentUpdate.shipment_id.in_(legacy_shipments)))
    db.execute(delete(OperationalEvent).where(OperationalEvent.tenant_id == tenant_id))
    db.execute(
        delete(ProductionInterruptionImpactConfig).where(
            ProductionInterruptionImpactConfig.tenant_id == tenant_id,
            ProductionInterruptionImpactConfig.plant_id.in_(legacy_plants),
        )
    )
    db.execute(
        delete(PlantMaterialThreshold).where(
            PlantMaterialThreshold.tenant_id == tenant_id,
            PlantMaterialThreshold.plant_id.in_(legacy_plants),
        )
    )
    db.execute(
        delete(StockSnapshot).where(
            StockSnapshot.tenant_id == tenant_id,
            StockSnapshot.plant_id.in_(legacy_plants),
        )
    )
    db.execute(delete(Shipment).where(Shipment.id.in_(legacy_shipments)))
    db.execute(
        delete(ExternalDataSource).where(
            ExternalDataSource.tenant_id == tenant_id,
            ExternalDataSource.source_name.in_(LEGACY_SOURCE_NAMES),
        )
    )


def seed() -> None:
    db = SessionLocal()
    try:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "demo-steel"))
        if tenant is None:
            tenant = Tenant(
                name="Demo Steel Plant",
                slug="demo-steel",
                is_demo_tenant=True,
            )
            db.add(tenant)
            db.flush()
        else:
            tenant.name = "Demo Steel Plant"
            tenant.is_demo_tenant = True

        roles = {role_name: get_or_create_role(db, role_name) for role_name in ROLE_NAMES}
        superadmin = get_or_create_superadmin(db)
        for email, full_name, role_name in DEMO_USERS:
            user = get_or_create_user(db, email, full_name)
            membership = db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant.id,
                    TenantMembership.user_id == user.id,
                )
            )
            if membership is None:
                db.add(
                    TenantMembership(
                        tenant_id=tenant.id,
                        user_id=user.id,
                        role_id=roles[role_name].id,
                        is_active=True,
                    )
                )
            else:
                membership.role_id = roles[role_name].id
                membership.is_active = True

        db.execute(delete(TenantMembership).where(TenantMembership.user_id == superadmin.id))
        cleanup_legacy_demo_operational_data(db, tenant.id)
        db.commit()
        print(
            "Prepared demo-steel tenant and removed legacy demo operational rows. "
            "Use docs/demo-data uploads or guarded Risk Workspace scenarios for current demos."
        )
        print("Demo password for tenant users: Password123!")
        print("Superadmin login: superadmin@opsdeck.local / SuperAdmin123! (no tenant membership)")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
