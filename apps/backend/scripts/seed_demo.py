from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    ExceptionCase,
    ExceptionComment,
    ExternalDataSource,
    InlandMovement,
    LineStopIncident,
    Material,
    Plant,
    PlantMaterialThreshold,
    PortEvent,
    Role,
    Shipment,
    StockSnapshot,
    Supplier,
    Tenant,
    TenantMembership,
    User,
)
from app.models.enums import ExceptionSeverity, ExceptionStatus, ExceptionType, ShipmentState
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
    TENANT_ADMIN: "Tenant administrator with full control tower access",
    BUYER_USER: "Buyer responsible for supplier and inbound coordination",
    LOGISTICS_USER: "Logistics operator responsible for inbound movement execution",
    PLANNER_USER: "Planner responsible for material availability and ETA planning",
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
    user = db.scalar(
        select(User).where(
            User.email.in_(["superadmin@opsdeck.local", "superadmin@steelops.local"])
        )
    )
    if user:
        user.email = "superadmin@opsdeck.local"
        user.full_name = "OpsDeck Superadmin"
        if not user.is_superadmin:
            user.is_superadmin = True
        return user

    user = User(
        email="superadmin@opsdeck.local",
        full_name="OpsDeck Superadmin",
        password_hash=hash_password("SuperAdmin123!"),
        is_active=True,
        is_superadmin=True,
    )
    db.add(user)
    db.flush()
    return user


def get_or_create_plant(db: Session, tenant_id: int, code: str, name: str, location: str) -> Plant:
    plant = db.scalar(select(Plant).where(Plant.tenant_id == tenant_id, Plant.code == code))
    if plant:
        return plant

    plant = Plant(tenant_id=tenant_id, code=code, name=name, location=location)
    db.add(plant)
    db.flush()
    return plant


def get_or_create_material(
    db: Session,
    tenant_id: int,
    code: str,
    name: str,
    category: str,
) -> Material:
    material = db.scalar(
        select(Material).where(Material.tenant_id == tenant_id, Material.code == code)
    )
    if material:
        return material

    material = Material(tenant_id=tenant_id, code=code, name=name, category=category, uom="MT")
    db.add(material)
    db.flush()
    return material


def ensure_threshold(
    db: Session,
    tenant_id: int,
    plant_id: int,
    material_id: int,
    threshold_days: Decimal,
    warning_days: Decimal,
) -> None:
    threshold = db.scalar(
        select(PlantMaterialThreshold).where(
            PlantMaterialThreshold.tenant_id == tenant_id,
            PlantMaterialThreshold.plant_id == plant_id,
            PlantMaterialThreshold.material_id == material_id,
        )
    )
    if threshold:
        return

    db.add(
        PlantMaterialThreshold(
            tenant_id=tenant_id,
            plant_id=plant_id,
            material_id=material_id,
            threshold_days=threshold_days,
            warning_days=warning_days,
        )
    )


def get_or_create_supplier(
    db: Session,
    tenant_id: int,
    *,
    name: str,
    code: str,
    primary_port: str,
    secondary_ports: list[str],
    material_categories: list[str],
    country: str,
    contact_name: str,
    contact_email: str,
) -> Supplier:
    supplier = db.scalar(select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.code == code))
    if supplier is None:
        supplier = Supplier(tenant_id=tenant_id, name=name, code=code)
        db.add(supplier)
        db.flush()
    supplier.name = name
    supplier.primary_port = primary_port
    supplier.secondary_ports = secondary_ports
    supplier.material_categories = material_categories
    supplier.country_of_origin = country
    supplier.contact_name = contact_name
    supplier.contact_email = contact_email
    supplier.is_active = True
    return supplier


def upsert_stock_snapshot(
    db: Session,
    tenant_id: int,
    plant_id: int,
    material_id: int,
    *,
    on_hand_mt: Decimal,
    quality_held_mt: Decimal,
    available_to_consume_mt: Decimal,
    daily_consumption_mt: Decimal,
    snapshot_time: datetime,
) -> None:
    db.execute(
        delete(StockSnapshot).where(
            StockSnapshot.tenant_id == tenant_id,
            StockSnapshot.plant_id == plant_id,
            StockSnapshot.material_id == material_id,
        )
    )
    db.add(
        StockSnapshot(
            tenant_id=tenant_id,
            plant_id=plant_id,
            material_id=material_id,
            on_hand_mt=on_hand_mt,
            quality_held_mt=quality_held_mt,
            available_to_consume_mt=available_to_consume_mt,
            daily_consumption_mt=daily_consumption_mt,
            snapshot_time=snapshot_time,
        )
    )


def upsert_shipment(
    db: Session,
    tenant_id: int,
    *,
    shipment_id: str,
    material_id: int,
    plant_id: int,
    supplier: Supplier,
    quantity_mt: Decimal,
    vessel_name: str | None,
    imo_number: str | None,
    mmsi: str | None,
    origin_port: str,
    destination_port: str,
    planned_eta: datetime,
    current_eta: datetime,
    eta_confidence: Decimal,
    current_state: ShipmentState,
    latest_update_at: datetime,
) -> Shipment:
    shipment = db.scalar(
        select(Shipment).where(Shipment.tenant_id == tenant_id, Shipment.shipment_id == shipment_id)
    )
    if shipment is None:
        shipment = Shipment(
            tenant_id=tenant_id,
            shipment_id=shipment_id,
            material_id=material_id,
            plant_id=plant_id,
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            quantity_mt=quantity_mt,
            vessel_name=vessel_name,
            imo_number=imo_number,
            mmsi=mmsi,
            origin_port=origin_port,
            destination_port=destination_port,
            planned_eta=planned_eta,
            current_eta=current_eta,
            eta_confidence=eta_confidence,
            current_state=current_state,
            source_of_truth="demo_seed",
            latest_update_at=latest_update_at,
        )
        db.add(shipment)
        db.flush()
    else:
        shipment.material_id = material_id
        shipment.plant_id = plant_id
        shipment.supplier_id = supplier.id
        shipment.supplier_name = supplier.name
        shipment.quantity_mt = quantity_mt
        shipment.vessel_name = vessel_name
        shipment.imo_number = imo_number
        shipment.mmsi = mmsi
        shipment.origin_port = origin_port
        shipment.destination_port = destination_port
        shipment.planned_eta = planned_eta
        shipment.current_eta = current_eta
        shipment.eta_confidence = eta_confidence
        shipment.current_state = current_state
        shipment.source_of_truth = "demo_seed"
        shipment.latest_update_at = latest_update_at
    return shipment


def replace_port_event(db: Session, tenant_id: int, shipment: Shipment, **values: object) -> None:
    db.execute(delete(PortEvent).where(PortEvent.tenant_id == tenant_id, PortEvent.shipment_id == shipment.id))
    db.add(PortEvent(tenant_id=tenant_id, shipment_id=shipment.id, **values))


def replace_inland_movement(db: Session, tenant_id: int, shipment: Shipment, **values: object) -> None:
    db.execute(
        delete(InlandMovement).where(
            InlandMovement.tenant_id == tenant_id,
            InlandMovement.shipment_id == shipment.id,
        )
    )
    db.add(InlandMovement(tenant_id=tenant_id, shipment_id=shipment.id, **values))


def seed_exception(
    db: Session,
    tenant_id: int,
    *,
    title: str,
    type_: ExceptionType,
    severity: ExceptionSeverity,
    status: ExceptionStatus,
    shipment: Shipment | None,
    plant_id: int,
    material_id: int,
    owner_user_id: int | None,
    triggered_at: datetime,
    due_at: datetime,
    next_action: str,
    action_status: str,
) -> None:
    existing = db.scalar(select(ExceptionCase).where(ExceptionCase.tenant_id == tenant_id, ExceptionCase.title == title))
    if existing is not None:
        db.execute(delete(ExceptionComment).where(ExceptionComment.exception_case_id == existing.id))
        db.delete(existing)
        db.flush()
    case = ExceptionCase(
        tenant_id=tenant_id,
        type=type_,
        severity=severity,
        status=status,
        title=title,
        summary=next_action,
        linked_shipment_id=shipment.id if shipment else None,
        linked_plant_id=plant_id,
        linked_material_id=material_id,
        owner_user_id=owner_user_id,
        triggered_at=triggered_at,
        due_at=due_at,
        next_action=next_action,
        action_status=action_status,
        action_started_at=triggered_at + timedelta(hours=1) if action_status != "pending" else None,
    )
    db.add(case)
    db.flush()
    db.add(
        ExceptionComment(
            tenant_id=tenant_id,
            exception_case_id=case.id,
            author_user_id=owner_user_id,
            comment="Demo note: owner has reviewed the signal and updated the recovery path.",
        )
    )


def seed() -> None:
    db = SessionLocal()
    try:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "demo-steel"))
        if tenant is None:
            tenant = Tenant(name="Demo Steel Plant", slug="demo-steel")
            db.add(tenant)
            db.flush()

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

        db.execute(delete(TenantMembership).where(TenantMembership.user_id == superadmin.id))

        jamshedpur = get_or_create_plant(
            db,
            tenant.id,
            "JAM",
            "Jamshedpur Integrated Steel Plant",
            "Jamshedpur, Jharkhand",
        )
        kalinga = get_or_create_plant(
            db,
            tenant.id,
            "KAL",
            "Kalinganagar Steel Plant",
            "Kalinganagar, Odisha",
        )
        coking_coal = get_or_create_material(
            db,
            tenant.id,
            "COKING_COAL",
            "Premium hard coking coal",
            "coal",
        )
        iron_ore = get_or_create_material(
            db,
            tenant.id,
            "IRON_ORE_FINES",
            "Iron ore fines",
            "ore",
        )
        limestone = get_or_create_material(
            db,
            tenant.id,
            "LIMESTONE",
            "Steel grade limestone",
            "flux",
        )
        dolomite = get_or_create_material(
            db,
            tenant.id,
            "DOLOMITE",
            "Blast furnace dolomite",
            "flux",
        )

        ensure_threshold(db, tenant.id, jamshedpur.id, coking_coal.id, Decimal("7"), Decimal("10"))
        ensure_threshold(db, tenant.id, jamshedpur.id, iron_ore.id, Decimal("5"), Decimal("8"))
        ensure_threshold(db, tenant.id, kalinga.id, limestone.id, Decimal("4"), Decimal("7"))
        ensure_threshold(db, tenant.id, kalinga.id, dolomite.id, Decimal("6"), Decimal("9"))

        now = datetime.now(UTC)
        users = {
            membership.role.name: db.get(User, membership.user_id)
            for membership in db.scalars(
                select(TenantMembership).where(TenantMembership.tenant_id == tenant.id)
            )
            if membership.role is not None
        }
        bhp = get_or_create_supplier(
            db,
            tenant.id,
            name="BHP Mitsubishi Alliance",
            code="BHPMA",
            primary_port="Hay Point",
            secondary_ports=["Gladstone", "Abbot Point"],
            material_categories=["coal"],
            country="Australia",
            contact_name="Ava McKenzie",
            contact_email="ava.mckenzie@bhpma.example",
        )
        odisha = get_or_create_supplier(
            db,
            tenant.id,
            name="Odisha Mining Corp",
            code="OMC",
            primary_port="Barbil Rail Siding",
            secondary_ports=["Joda", "Banspani"],
            material_categories=["ore"],
            country="India",
            contact_name="Rahul Patnaik",
            contact_email="rahul.patnaik@omc.example",
        )
        rsmml = get_or_create_supplier(
            db,
            tenant.id,
            name="RSMML",
            code="RSMML",
            primary_port="Jaisalmer Yard",
            secondary_ports=["Limestone Yard", "Kandla"],
            material_categories=["flux"],
            country="India",
            contact_name="Meera Singh",
            contact_email="meera.singh@rsmml.example",
        )
        vale = get_or_create_supplier(
            db,
            tenant.id,
            name="Vale International",
            code="VALE",
            primary_port="Ponta da Madeira",
            secondary_ports=["Tubarao", "Visakhapatnam"],
            material_categories=["ore"],
            country="Brazil",
            contact_name="Lucas Ferreira",
            contact_email="lucas.ferreira@vale.example",
        )

        upsert_stock_snapshot(
            db,
            tenant.id,
            jamshedpur.id,
            coking_coal.id,
            on_hand_mt=Decimal("8500"),
            quality_held_mt=Decimal("2500"),
            available_to_consume_mt=Decimal("6000"),
            daily_consumption_mt=Decimal("4200"),
            snapshot_time=now - timedelta(hours=3),
        )
        upsert_stock_snapshot(
            db,
            tenant.id,
            jamshedpur.id,
            iron_ore.id,
            on_hand_mt=Decimal("74000"),
            quality_held_mt=Decimal("5000"),
            available_to_consume_mt=Decimal("69000"),
            daily_consumption_mt=Decimal("9500"),
            snapshot_time=now - timedelta(hours=2),
        )
        upsert_stock_snapshot(
            db,
            tenant.id,
            kalinga.id,
            limestone.id,
            on_hand_mt=Decimal("3300"),
            quality_held_mt=Decimal("800"),
            available_to_consume_mt=Decimal("2500"),
            daily_consumption_mt=Decimal("2100"),
            snapshot_time=now - timedelta(hours=5),
        )
        upsert_stock_snapshot(
            db,
            tenant.id,
            kalinga.id,
            dolomite.id,
            on_hand_mt=Decimal("36000"),
            quality_held_mt=Decimal("0"),
            available_to_consume_mt=Decimal("36000"),
            daily_consumption_mt=Decimal("3200"),
            snapshot_time=now - timedelta(hours=4),
        )

        coal_shipment = upsert_shipment(
            db,
            tenant.id,
            shipment_id="SHP-COAL-001",
            material_id=coking_coal.id,
            plant_id=jamshedpur.id,
            supplier=bhp,
            quantity_mt=Decimal("74000"),
            vessel_name="MV Eastern Furnace",
            imo_number="9876543",
            mmsi="419000123",
            origin_port="Hay Point",
            destination_port="Paradip",
            planned_eta=now + timedelta(days=3),
            current_eta=now + timedelta(days=5),
            eta_confidence=Decimal("62.50"),
            current_state=ShipmentState.AT_PORT,
            latest_update_at=now - timedelta(days=5),
        )
        ore_shipment = upsert_shipment(
            db,
            tenant.id,
            shipment_id="SHP-ORE-002",
            material_id=iron_ore.id,
            plant_id=jamshedpur.id,
            supplier=odisha,
            quantity_mt=Decimal("52000"),
            vessel_name=None,
            imo_number=None,
            mmsi=None,
            origin_port="Barbil Rail Siding",
            destination_port="Jamshedpur Yard",
            planned_eta=now + timedelta(days=1),
            current_eta=now + timedelta(days=1, hours=5),
            eta_confidence=Decimal("91.00"),
            current_state=ShipmentState.INLAND_TRANSIT,
            latest_update_at=now - timedelta(hours=8),
        )
        lime_shipment = upsert_shipment(
            db,
            tenant.id,
            shipment_id="SHP-LIME-003",
            material_id=limestone.id,
            plant_id=kalinga.id,
            supplier=rsmml,
            quantity_mt=Decimal("18000"),
            vessel_name=None,
            imo_number=None,
            mmsi=None,
            origin_port="Jaisalmer Yard",
            destination_port="Kalinganagar Yard",
            planned_eta=now + timedelta(hours=10),
            current_eta=now + timedelta(hours=38),
            eta_confidence=Decimal("58.00"),
            current_state=ShipmentState.DELAYED,
            latest_update_at=now - timedelta(days=6),
        )
        dolomite_shipment = upsert_shipment(
            db,
            tenant.id,
            shipment_id="SHP-DOLO-004",
            material_id=dolomite.id,
            plant_id=kalinga.id,
            supplier=rsmml,
            quantity_mt=Decimal("24000"),
            vessel_name=None,
            imo_number=None,
            mmsi=None,
            origin_port="Kandla",
            destination_port="Kalinganagar Yard",
            planned_eta=now + timedelta(days=6),
            current_eta=now + timedelta(days=6, hours=4),
            eta_confidence=Decimal("86.00"),
            current_state=ShipmentState.IN_TRANSIT,
            latest_update_at=now - timedelta(hours=5),
        )
        vale_shipment = upsert_shipment(
            db,
            tenant.id,
            shipment_id="SHP-ORE-005",
            material_id=iron_ore.id,
            plant_id=kalinga.id,
            supplier=vale,
            quantity_mt=Decimal("90000"),
            vessel_name="MV Atlantic Charge",
            imo_number="9345678",
            mmsi="710000456",
            origin_port="Ponta da Madeira",
            destination_port="Visakhapatnam",
            planned_eta=now + timedelta(days=9),
            current_eta=now + timedelta(days=9, hours=8),
            eta_confidence=Decimal("89.00"),
            current_state=ShipmentState.IN_TRANSIT,
            latest_update_at=now - timedelta(hours=2),
        )

        replace_port_event(
            db,
            tenant.id,
            coal_shipment,
            berth_status="waiting",
            waiting_days=Decimal("3.25"),
            discharge_started_at=None,
            discharge_rate_mt_per_day=None,
            estimated_demurrage_exposure=Decimal("145000"),
            updated_at=now - timedelta(days=5),
        )
        replace_port_event(
            db,
            tenant.id,
            vale_shipment,
            berth_status="expected",
            waiting_days=Decimal("0.25"),
            discharge_started_at=None,
            discharge_rate_mt_per_day=Decimal("18000"),
            estimated_demurrage_exposure=Decimal("0"),
            updated_at=now - timedelta(hours=2),
        )
        replace_inland_movement(
            db,
            tenant.id,
            ore_shipment,
            mode="rail",
            carrier_name="Indian Railways",
            origin_location="Barbil Rail Siding",
            destination_location="Jamshedpur Yard",
            planned_departure_at=now - timedelta(days=2),
            planned_arrival_at=now - timedelta(hours=10),
            actual_departure_at=now - timedelta(days=2),
            actual_arrival_at=None,
            current_state="en_route",
            updated_at=now - timedelta(hours=8),
        )
        replace_inland_movement(
            db,
            tenant.id,
            lime_shipment,
            mode="truck",
            carrier_name="Eastern Roadlines",
            origin_location="Jaisalmer Yard",
            destination_location="Kalinganagar Yard",
            planned_departure_at=now - timedelta(days=4),
            planned_arrival_at=now - timedelta(days=1),
            actual_departure_at=now - timedelta(days=4),
            actual_arrival_at=None,
            current_state="delayed_at_checkpoint",
            updated_at=now - timedelta(days=6),
        )

        db.execute(delete(ExceptionCase).where(ExceptionCase.tenant_id == tenant.id))
        logistics_user = users.get(LOGISTICS_USER)
        planner_user = users.get(PLANNER_USER)
        buyer_user = users.get(BUYER_USER)
        seed_exception(
            db,
            tenant.id,
            title="Coal vessel waiting at Paradip berth window",
            type_=ExceptionType.DEMURRAGE_RISK,
            severity=ExceptionSeverity.CRITICAL,
            status=ExceptionStatus.IN_PROGRESS,
            shipment=coal_shipment,
            plant_id=jamshedpur.id,
            material_id=coking_coal.id,
            owner_user_id=logistics_user.id if logistics_user else None,
            triggered_at=now - timedelta(days=2),
            due_at=now + timedelta(hours=6),
            next_action="Escalate berth confirmation and secure discharge gang before night shift.",
            action_status="in_progress",
        )
        seed_exception(
            db,
            tenant.id,
            title="Limestone inbound delay risks Kalinganagar flux cover",
            type_=ExceptionType.ETA_RISK,
            severity=ExceptionSeverity.HIGH,
            status=ExceptionStatus.OPEN,
            shipment=lime_shipment,
            plant_id=kalinga.id,
            material_id=limestone.id,
            owner_user_id=planner_user.id if planner_user else None,
            triggered_at=now - timedelta(hours=18),
            due_at=now + timedelta(hours=12),
            next_action="Rebalance flux drawdown and confirm alternate trucking slot with RSMML.",
            action_status="pending",
        )
        seed_exception(
            db,
            tenant.id,
            title="Coking coal stock below critical cover",
            type_=ExceptionType.STOCKOUT_RISK,
            severity=ExceptionSeverity.CRITICAL,
            status=ExceptionStatus.OPEN,
            shipment=coal_shipment,
            plant_id=jamshedpur.id,
            material_id=coking_coal.id,
            owner_user_id=buyer_user.id if buyer_user else None,
            triggered_at=now - timedelta(hours=10),
            due_at=now + timedelta(hours=4),
            next_action="Approve emergency blend substitution until vessel discharge begins.",
            action_status="pending",
        )

        db.execute(delete(LineStopIncident).where(LineStopIncident.tenant_id == tenant.id))
        db.add_all(
            [
                LineStopIncident(
                    tenant_id=tenant.id,
                    plant_id=jamshedpur.id,
                    material_id=coking_coal.id,
                    stopped_at=now - timedelta(days=9),
                    duration_hours=Decimal("2.50"),
                    notes="Blast furnace feed slowed during coal blend shortage.",
                ),
                LineStopIncident(
                    tenant_id=tenant.id,
                    plant_id=kalinga.id,
                    material_id=limestone.id,
                    stopped_at=now - timedelta(days=3),
                    duration_hours=Decimal("1.25"),
                    notes="Flux staging interruption during truck delay.",
                ),
            ]
        )

        source = db.scalar(
            select(ExternalDataSource).where(
                ExternalDataSource.tenant_id == tenant.id,
                ExternalDataSource.source_name == "Demo ERP inbound feed",
            )
        )
        if source is None:
            source = ExternalDataSource(
                tenant_id=tenant.id,
                source_type="excel_online",
                source_url="https://example.invalid/demo-inbound.xlsx",
                source_name="Demo ERP inbound feed",
                dataset_type="shipment",
            )
            db.add(source)
        source.sync_frequency_minutes = 60
        source.is_active = True
        source.last_sync_status = "success"
        source.last_synced_at = now - timedelta(minutes=18)
        source.new_critical_risks_count = 2
        source.resolved_risks_count = 1
        source.newly_breached_actions_count = 1

        db.commit()
        print("Seeded full OpsDeck MVP demo tenant with stock, suppliers, shipments, movement, exceptions, line stops, and sync freshness.")
        print("Demo password for tenant users: Password123!")
        print("Superadmin login: superadmin@opsdeck.local / SuperAdmin123! (no tenant membership)")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
