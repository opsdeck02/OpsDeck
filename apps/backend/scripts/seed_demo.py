from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    AuditLog,
    ExceptionCase,
    ExceptionComment,
    ExternalDataSource,
    ImportJobRecord,
    IngestionJob,
    InlandMovement,
    LineStopIncident,
    Material,
    MaterialProcessDependency,
    OperationalEvent,
    Plant,
    PlantMaterialThreshold,
    PortEvent,
    ProcessProductDependency,
    ProductionInterruptionImpactConfig,
    ProductionLine,
    Role,
    Shipment,
    ShipmentInboundTrustConfig,
    ShipmentUpdate,
    StockSnapshot,
    Supplier,
    Tenant,
    TenantMembership,
    UploadedFile,
    User,
)
from app.models.enums import ShipmentState
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

DEMO_PLANT_CODE = "DEMO-STEEL"


@dataclass(frozen=True)
class DemoMaterialConfig:
    code: str
    name: str
    category: str
    supplier_code: str
    supplier_name: str
    supplier_origin: str
    primary_port: str
    stock_on_hand: Decimal
    quality_held: Decimal
    available_stock: Decimal
    daily_consumption: Decimal
    critical_days: Decimal
    warning_days: Decimal
    stockout_horizon_days: Decimal
    production_line_code: str
    production_line_name: str
    production_rate_mt_per_hour: Decimal
    finished_goods_value_per_mt: Decimal
    survivable_hours: Decimal
    line_dependency_ratio: Decimal
    downtime_cost_per_hour: Decimal
    restart_cost: Decimal
    restart_time_hours: Decimal
    substitution_factor: Decimal
    cascading_impact_factor: Decimal
    dependency_ratio: Decimal
    product_name: str
    output_share_ratio: Decimal
    product_value_per_mt: Decimal
    operational_criticality_factor: Decimal
    visibility_profile: str
    visibility_cadence_hours: Decimal
    eta_drift_tolerance_hours: Decimal
    weak_visibility_threshold: Decimal
    minimum_trusted_inbound_ratio: Decimal
    active_shipment_state: str
    active_shipment_quantity: Decimal
    active_shipment_eta_days: int
    active_shipment_delay_days: int
    vessel_name: str | None
    imo_number: str | None
    mmsi: str | None
    origin_port: str
    destination_port: str
    current_milestone: str
    current_location: str
    eta_confidence: Decimal


DEMO_MATERIALS = (
    DemoMaterialConfig(
        code="DEMO-COKING-COAL",
        name="Imported Coking Coal",
        category="raw_material",
        supplier_code="DEMO-SUPPLIER-COAL-01",
        supplier_name="Eastern Metallurgical Coal",
        supplier_origin="Australia",
        primary_port="Hay Point",
        stock_on_hand=Decimal("100"),
        quality_held=Decimal("0"),
        available_stock=Decimal("100"),
        daily_consumption=Decimal("10"),
        critical_days=Decimal("1"),
        warning_days=Decimal("5"),
        stockout_horizon_days=Decimal("7"),
        production_line_code="BF-1",
        production_line_name="Blast Furnace 1",
        production_rate_mt_per_hour=Decimal("210"),
        finished_goods_value_per_mt=Decimal("62000"),
        survivable_hours=Decimal("10"),
        line_dependency_ratio=Decimal("0.95"),
        downtime_cost_per_hour=Decimal("18500000"),
        restart_cost=Decimal("42000000"),
        restart_time_hours=Decimal("8"),
        substitution_factor=Decimal("0.08"),
        cascading_impact_factor=Decimal("1.35"),
        dependency_ratio=Decimal("0.95"),
        product_name="Hot Metal",
        output_share_ratio=Decimal("1.00"),
        product_value_per_mt=Decimal("62000"),
        operational_criticality_factor=Decimal("1.40"),
        visibility_profile="ocean",
        visibility_cadence_hours=Decimal("48"),
        eta_drift_tolerance_hours=Decimal("36"),
        weak_visibility_threshold=Decimal("0.55"),
        minimum_trusted_inbound_ratio=Decimal("0.65"),
        active_shipment_state="delayed",
        active_shipment_quantity=Decimal("10"),
        active_shipment_eta_days=2,
        active_shipment_delay_days=0,
        vessel_name="MV Eastern Line",
        imo_number="9876543",
        mmsi="419000123",
        origin_port="Hay Point",
        destination_port="Paradip",
        current_milestone="ocean_transit",
        current_location="Bay of Bengal",
        eta_confidence=Decimal("0.72"),
    ),
    DemoMaterialConfig(
        code="DEMO-LIMESTONE",
        name="BF Grade Limestone",
        category="flux",
        supplier_code="DEMO-SUPPLIER-LIME-03",
        supplier_name="Rourkela Minerals",
        supplier_origin="India",
        primary_port="Rourkela",
        stock_on_hand=Decimal("8900"),
        quality_held=Decimal("250"),
        available_stock=Decimal("8650"),
        daily_consumption=Decimal("2100"),
        critical_days=Decimal("4"),
        warning_days=Decimal("14"),
        stockout_horizon_days=Decimal("10"),
        production_line_code="BF-1",
        production_line_name="Blast Furnace 1",
        production_rate_mt_per_hour=Decimal("210"),
        finished_goods_value_per_mt=Decimal("62000"),
        survivable_hours=Decimal("18"),
        line_dependency_ratio=Decimal("0.72"),
        downtime_cost_per_hour=Decimal("7200000"),
        restart_cost=Decimal("12000000"),
        restart_time_hours=Decimal("4"),
        substitution_factor=Decimal("0.22"),
        cascading_impact_factor=Decimal("1.10"),
        dependency_ratio=Decimal("0.72"),
        product_name="Hot Metal",
        output_share_ratio=Decimal("1.00"),
        product_value_per_mt=Decimal("62000"),
        operational_criticality_factor=Decimal("1.10"),
        visibility_profile="inland",
        visibility_cadence_hours=Decimal("24"),
        eta_drift_tolerance_hours=Decimal("12"),
        weak_visibility_threshold=Decimal("0.45"),
        minimum_trusted_inbound_ratio=Decimal("0.55"),
        active_shipment_state="inland_transit",
        active_shipment_quantity=Decimal("6500"),
        active_shipment_eta_days=2,
        active_shipment_delay_days=0,
        vessel_name=None,
        imo_number=None,
        mmsi=None,
        origin_port="Rourkela",
        destination_port="Jamshedpur",
        current_milestone="rail_inland",
        current_location="Tatanagar approach",
        eta_confidence=Decimal("0.86"),
    ),
    DemoMaterialConfig(
        code="DEMO-PELLET-FINES",
        name="Iron Ore Pellet Fines",
        category="raw_material",
        supplier_code="DEMO-SUPPLIER-PELLET-02",
        supplier_name="Vizag Pellet Works",
        supplier_origin="India",
        primary_port="Visakhapatnam",
        stock_on_hand=Decimal("11200"),
        quality_held=Decimal("700"),
        available_stock=Decimal("10500"),
        daily_consumption=Decimal("5200"),
        critical_days=Decimal("2"),
        warning_days=Decimal("7"),
        stockout_horizon_days=Decimal("5"),
        production_line_code="DRI-1",
        production_line_name="Direct Reduction Kiln 1",
        production_rate_mt_per_hour=Decimal("85"),
        finished_goods_value_per_mt=Decimal("48500"),
        survivable_hours=Decimal("8"),
        line_dependency_ratio=Decimal("0.88"),
        downtime_cost_per_hour=Decimal("6200000"),
        restart_cost=Decimal("9000000"),
        restart_time_hours=Decimal("5"),
        substitution_factor=Decimal("0.12"),
        cascading_impact_factor=Decimal("1.20"),
        dependency_ratio=Decimal("0.88"),
        product_name="Sponge Iron",
        output_share_ratio=Decimal("1.00"),
        product_value_per_mt=Decimal("48500"),
        operational_criticality_factor=Decimal("1.25"),
        visibility_profile="inland",
        visibility_cadence_hours=Decimal("18"),
        eta_drift_tolerance_hours=Decimal("10"),
        weak_visibility_threshold=Decimal("0.50"),
        minimum_trusted_inbound_ratio=Decimal("0.60"),
        active_shipment_state="inland_transit",
        active_shipment_quantity=Decimal("4800"),
        active_shipment_eta_days=1,
        active_shipment_delay_days=1,
        vessel_name=None,
        imo_number=None,
        mmsi=None,
        origin_port="Visakhapatnam",
        destination_port="Raipur",
        current_milestone="rake_departed",
        current_location="Titlagarh",
        eta_confidence=Decimal("0.78"),
    ),
    DemoMaterialConfig(
        code="DEMO-FERRO-MANGANESE",
        name="High Carbon Ferro Manganese",
        category="alloy",
        supplier_code="DEMO-SUPPLIER-ALLOY-04",
        supplier_name="Nagpur Alloy House",
        supplier_origin="India",
        primary_port="Nagpur",
        stock_on_hand=Decimal("420"),
        quality_held=Decimal("20"),
        available_stock=Decimal("400"),
        daily_consumption=Decimal("95"),
        critical_days=Decimal("5"),
        warning_days=Decimal("15"),
        stockout_horizon_days=Decimal("12"),
        production_line_code="SMS-1",
        production_line_name="Steel Melting Shop 1",
        production_rate_mt_per_hour=Decimal("115"),
        finished_goods_value_per_mt=Decimal("71000"),
        survivable_hours=Decimal("20"),
        line_dependency_ratio=Decimal("0.64"),
        downtime_cost_per_hour=Decimal("5100000"),
        restart_cost=Decimal("7000000"),
        restart_time_hours=Decimal("3"),
        substitution_factor=Decimal("0.18"),
        cascading_impact_factor=Decimal("1.05"),
        dependency_ratio=Decimal("0.64"),
        product_name="Billet",
        output_share_ratio=Decimal("1.00"),
        product_value_per_mt=Decimal("71000"),
        operational_criticality_factor=Decimal("1.05"),
        visibility_profile="inland",
        visibility_cadence_hours=Decimal("12"),
        eta_drift_tolerance_hours=Decimal("8"),
        weak_visibility_threshold=Decimal("0.50"),
        minimum_trusted_inbound_ratio=Decimal("0.60"),
        active_shipment_state="in_transit",
        active_shipment_quantity=Decimal("260"),
        active_shipment_eta_days=2,
        active_shipment_delay_days=0,
        vessel_name=None,
        imo_number=None,
        mmsi=None,
        origin_port="Nagpur",
        destination_port="Raipur",
        current_milestone="truck_verified",
        current_location="Bhandara",
        eta_confidence=Decimal("0.92"),
    ),
)


def get_or_create_role(db: Session, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role:
        return role
    role = Role(name=name, description=ROLE_DESCRIPTIONS[name])
    db.add(role)
    flush_pending(db)
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
    flush_pending(db)
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
        flush_pending(db)
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


def reset_demo_operational_data(db: Session, tenant_id: int) -> None:
    shipment_ids = select(Shipment.id).where(Shipment.tenant_id == tenant_id)
    ingestion_job_ids = select(IngestionJob.id).where(IngestionJob.tenant_id == tenant_id)

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
    db.execute(delete(ShipmentUpdate).where(ShipmentUpdate.shipment_id.in_(shipment_ids)))
    db.execute(delete(OperationalEvent).where(OperationalEvent.tenant_id == tenant_id))
    db.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant_id))
    db.execute(delete(ImportJobRecord).where(ImportJobRecord.import_job_id.in_(ingestion_job_ids)))
    db.execute(delete(IngestionJob).where(IngestionJob.tenant_id == tenant_id))
    db.execute(delete(UploadedFile).where(UploadedFile.tenant_id == tenant_id))
    db.execute(delete(ExternalDataSource).where(ExternalDataSource.tenant_id == tenant_id))
    db.execute(delete(Shipment).where(Shipment.tenant_id == tenant_id))
    db.execute(delete(StockSnapshot).where(StockSnapshot.tenant_id == tenant_id))
    db.execute(delete(PlantMaterialThreshold).where(PlantMaterialThreshold.tenant_id == tenant_id))
    db.execute(
        delete(ProductionInterruptionImpactConfig).where(
            ProductionInterruptionImpactConfig.tenant_id == tenant_id
        )
    )
    db.execute(
        delete(MaterialProcessDependency).where(MaterialProcessDependency.tenant_id == tenant_id)
    )
    db.execute(
        delete(ProcessProductDependency).where(ProcessProductDependency.tenant_id == tenant_id)
    )
    db.execute(
        delete(ShipmentInboundTrustConfig).where(
            ShipmentInboundTrustConfig.tenant_id == tenant_id
        )
    )
    db.execute(delete(ProductionLine).where(ProductionLine.tenant_id == tenant_id))


def stamp_pending_rows(db: Session, now: datetime) -> None:
    for row in db.new:
        if hasattr(row, "created_at") and getattr(row, "created_at", None) is None:
            row.created_at = now
        if hasattr(row, "updated_at") and getattr(row, "updated_at", None) is None:
            row.updated_at = now


def flush_pending(db: Session, now: datetime | None = None) -> None:
    stamp_pending_rows(db, now or datetime.now(UTC).replace(microsecond=0))
    db.flush()


def upsert_plant(db: Session, tenant_id: int) -> Plant:
    plant = db.scalar(
        select(Plant).where(
            Plant.tenant_id == tenant_id,
            Plant.code == DEMO_PLANT_CODE,
        )
    )
    if plant is None:
        plant = Plant(
            tenant_id=tenant_id,
            code=DEMO_PLANT_CODE,
            name="Demo Steel Plant - Integrated Works",
            location="Jamshedpur, Jharkhand, India",
        )
        db.add(plant)
        flush_pending(db)
    else:
        plant.name = "Demo Steel Plant - Integrated Works"
        plant.location = "Jamshedpur, Jharkhand, India"
    return plant


def upsert_material(db: Session, tenant_id: int, config: DemoMaterialConfig) -> Material:
    material = db.scalar(
        select(Material).where(
            Material.tenant_id == tenant_id,
            Material.code == config.code,
        )
    )
    if material is None:
        material = Material(
            tenant_id=tenant_id,
            code=config.code,
            name=config.name,
            category=config.category,
            uom="MT",
        )
        db.add(material)
        flush_pending(db)
    else:
        material.name = config.name
        material.category = config.category
        material.uom = "MT"
    return material


def upsert_supplier(db: Session, tenant_id: int, config: DemoMaterialConfig) -> Supplier:
    supplier = db.scalar(
        select(Supplier).where(
            Supplier.tenant_id == tenant_id,
            Supplier.code == config.supplier_code,
        )
    )
    if supplier is None:
        supplier = Supplier(
            tenant_id=tenant_id,
            code=config.supplier_code,
            name=config.supplier_name,
        )
        db.add(supplier)
        flush_pending(db)
    supplier.name = config.supplier_name
    supplier.primary_port = config.primary_port
    supplier.secondary_ports = [config.origin_port]
    supplier.material_categories = [config.category]
    supplier.country_of_origin = config.supplier_origin
    supplier.contact_name = "Demo supply desk"
    supplier.contact_email = "supplier.desk@demo.opsdeck.local"
    supplier.is_active = True
    return supplier


def seed_full_demo_configuration(db: Session, tenant_id: int, admin_user_id: int) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    plant = upsert_plant(db, tenant_id)
    materials = []
    for config in DEMO_MATERIALS:
        material = upsert_material(db, tenant_id, config)
        supplier = upsert_supplier(db, tenant_id, config)
        materials.append(material)
        seed_material_context(
            db,
            tenant_id=tenant_id,
            plant=plant,
            material=material,
            supplier=supplier,
            config=config,
            now=now,
        )
    seed_onboarding_records(db, tenant_id=tenant_id, admin_user_id=admin_user_id, now=now)
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=admin_user_id,
            action="exception.evaluation_triggered",
            entity_type="tenant",
            entity_id=str(tenant_id),
            metadata_json='{"source":"demo_seed","result":"complete_demo_ready"}',
        )
    )
    print(
        f"Seeded full operational demo for {len(materials)} materials at "
        "Demo Steel Plant."
    )


def seed_material_context(
    db: Session,
    *,
    tenant_id: int,
    plant: Plant,
    material: Material,
    supplier: Supplier,
    config: DemoMaterialConfig,
    now: datetime,
) -> None:
    stock_snapshot_time = now - timedelta(hours=2)
    reserve_days = Decimal("2") if config.code == "DEMO-COKING-COAL" else config.critical_days
    db.add(
        StockSnapshot(
            tenant_id=tenant_id,
            plant_id=plant.id,
            material_id=material.id,
            on_hand_mt=config.stock_on_hand,
            quality_held_mt=config.quality_held,
            available_to_consume_mt=config.available_stock,
            daily_consumption_mt=config.daily_consumption,
            snapshot_time=stock_snapshot_time,
        )
    )
    db.add(
        PlantMaterialThreshold(
            tenant_id=tenant_id,
            plant_id=plant.id,
            material_id=material.id,
            threshold_days=config.critical_days,
            warning_days=config.warning_days,
            minimum_buffer_stock_days=reserve_days,
            minimum_buffer_stock_mt=reserve_days * config.daily_consumption,
            stockout_alert_horizon_days=config.stockout_horizon_days,
        )
    )
    line = ProductionLine(
        tenant_id=tenant_id,
        plant_id=plant.id,
        code=config.production_line_code,
        name=config.production_line_name,
        is_active=True,
    )
    db.add(line)
    flush_pending(db)
    db.add(
        ProductionInterruptionImpactConfig(
            tenant_id=tenant_id,
            plant_id=plant.id,
            material_id=material.id,
            production_line_id=line.id,
            production_rate_mt_per_hour=config.production_rate_mt_per_hour,
            finished_goods_value_per_mt=config.finished_goods_value_per_mt,
            survivable_hours_without_material=config.survivable_hours,
            line_dependency_ratio=config.line_dependency_ratio,
            downtime_cost_per_hour=config.downtime_cost_per_hour,
            restart_cost=config.restart_cost,
            restart_time_hours=config.restart_time_hours,
            substitution_factor=config.substitution_factor,
            cascading_impact_factor=config.cascading_impact_factor,
            interruption_probability_override=None,
            currency="INR",
            is_active=True,
        )
    )
    db.add(
        MaterialProcessDependency(
            tenant_id=tenant_id,
            material_id=material.id,
            process_id=line.id,
            dependency_ratio=config.dependency_ratio,
            substitution_factor=config.substitution_factor,
            survivability_hours=config.survivable_hours,
            is_active=True,
        )
    )
    db.add(
        ProcessProductDependency(
            tenant_id=tenant_id,
            process_id=line.id,
            product_name=config.product_name,
            output_share_ratio=config.output_share_ratio,
            product_value_per_mt=config.product_value_per_mt,
            operational_criticality_factor=config.operational_criticality_factor,
            is_active=True,
        )
    )
    db.add(
        ShipmentInboundTrustConfig(
            tenant_id=tenant_id,
            plant_id=plant.id,
            material_id=material.id,
            visibility_profile=config.visibility_profile,
            expected_visibility_cadence_hours=config.visibility_cadence_hours,
            eta_drift_tolerance_hours=config.eta_drift_tolerance_hours,
            weak_visibility_threshold=config.weak_visibility_threshold,
            minimum_trusted_inbound_ratio=config.minimum_trusted_inbound_ratio,
            allow_unverified_inbound_protection=False,
            is_active=True,
        )
    )
    seed_shipments(
        db,
        tenant_id=tenant_id,
        plant=plant,
        material=material,
        supplier=supplier,
        config=config,
        now=now,
    )


def seed_shipments(
    db: Session,
    *,
    tenant_id: int,
    plant: Plant,
    material: Material,
    supplier: Supplier,
    config: DemoMaterialConfig,
    now: datetime,
) -> None:
    if config.code == "DEMO-COKING-COAL":
        seed_coking_coal_story_shipments(
            db,
            tenant_id=tenant_id,
            plant=plant,
            material=material,
            supplier=supplier,
            config=config,
            now=now,
        )
        return

    planned_eta = now + timedelta(
        days=max(1, config.active_shipment_eta_days - config.active_shipment_delay_days)
    )
    current_eta = now + timedelta(days=config.active_shipment_eta_days)
    active = Shipment(
        tenant_id=tenant_id,
        shipment_id=f"{config.code}-ACTIVE-01",
        plant_id=plant.id,
        material_id=material.id,
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        quantity_mt=config.active_shipment_quantity,
        vessel_name=config.vessel_name,
        imo_number=config.imo_number,
        mmsi=config.mmsi,
        origin_port=config.origin_port,
        destination_port=config.destination_port,
        planned_eta=planned_eta,
        current_eta=current_eta,
        latest_eta=current_eta,
        delay_days=config.active_shipment_delay_days,
        delay_status="delayed" if config.active_shipment_delay_days > 0 else "on_time",
        current_milestone=config.current_milestone,
        current_location=config.current_location,
        last_tracking_update_at=now - timedelta(hours=6),
        eta_confidence=config.eta_confidence,
        current_state=ShipmentState(config.active_shipment_state),
        source_of_truth="demo_onboarding",
        latest_update_at=now - timedelta(hours=4),
    )
    db.add(active)
    flush_pending(db)
    db.add(
        ShipmentUpdate(
            tenant_id=tenant_id,
            shipment_id=active.id,
            source="demo_onboarding",
            event_type="milestone_update",
            event_time=now - timedelta(hours=4),
            payload_json=None,
            notes=f"{active.shipment_id} seeded with verified operational context.",
        )
    )
    for index in range(1, 4):
        delivered_at = now - timedelta(days=14 + index * 9)
        db.add(
            Shipment(
                tenant_id=tenant_id,
                shipment_id=f"{config.code}-HIST-{index:02d}",
                plant_id=plant.id,
                material_id=material.id,
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                quantity_mt=(config.active_shipment_quantity * Decimal("0.85")).quantize(
                    Decimal("0.001")
                ),
                vessel_name=config.vessel_name,
                imo_number=config.imo_number,
                mmsi=config.mmsi,
                origin_port=config.origin_port,
                destination_port=config.destination_port,
                planned_eta=delivered_at - timedelta(hours=12),
                current_eta=delivered_at,
                latest_eta=delivered_at,
                delay_days=0,
                delay_status="on_time",
                current_milestone="delivered_to_plant",
                current_location=plant.location,
                last_tracking_update_at=delivered_at,
                eta_confidence=Decimal("0.90"),
                current_state=ShipmentState.DELIVERED,
                source_of_truth="demo_history",
                latest_update_at=delivered_at,
            )
        )


def seed_coking_coal_story_shipments(
    db: Session,
    *,
    tenant_id: int,
    plant: Plant,
    material: Material,
    supplier: Supplier,
    config: DemoMaterialConfig,
    now: datetime,
) -> None:
    story_shipments = (
        {
            "shipment_id": "DEMO-COAL-PROTECTIVE-A",
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "quantity_mt": Decimal("10"),
            "planned_eta": now + timedelta(days=2),
            "current_eta": now + timedelta(days=2),
            "latest_update_at": now - timedelta(hours=4),
            "last_tracking_update_at": now - timedelta(hours=4),
            "eta_confidence": Decimal("0.95"),
            "current_state": ShipmentState.IN_TRANSIT,
            "delay_days": 0,
            "delay_status": "on_time",
            "current_milestone": "ocean_transit",
            "current_location": "Bay of Bengal",
            "vessel_name": "MV Eastern Line",
            "imo_number": "9876543",
            "mmsi": "419000123",
            "origin_port": "Hay Point",
        },
        {
            "shipment_id": "DEMO-COAL-LATE-B",
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "quantity_mt": Decimal("10"),
            "planned_eta": now + timedelta(days=9),
            "current_eta": now + timedelta(days=9, hours=6),
            "latest_update_at": now - timedelta(hours=8),
            "last_tracking_update_at": now - timedelta(hours=8),
            "eta_confidence": Decimal("0.88"),
            "current_state": ShipmentState.IN_TRANSIT,
            "delay_days": 0,
            "delay_status": "watch",
            "current_milestone": "ocean_transit",
            "current_location": "Indian Ocean",
            "vessel_name": "MV Furnace Bay",
            "imo_number": "9765432",
            "mmsi": "419000456",
            "origin_port": "Newcastle",
        },
        {
            "shipment_id": "DEMO-COAL-TOO-LATE-C",
            "supplier_id": None,
            "supplier_name": "Unlinked Demo Coal Desk",
            "quantity_mt": Decimal("30"),
            "planned_eta": now + timedelta(days=13),
            "current_eta": now + timedelta(days=13),
            "latest_update_at": now - timedelta(hours=8),
            "last_tracking_update_at": now - timedelta(hours=8),
            "eta_confidence": Decimal("0.72"),
            "current_state": ShipmentState.PLANNED,
            "delay_days": 0,
            "delay_status": "planned",
            "current_milestone": "fixture_pending",
            "current_location": "Hay Point",
            "vessel_name": "MV Late Relief",
            "imo_number": "9654321",
            "mmsi": "419000789",
            "origin_port": "Hay Point",
        },
    )
    for item in story_shipments:
        shipment = Shipment(
            tenant_id=tenant_id,
            shipment_id=item["shipment_id"],
            plant_id=plant.id,
            material_id=material.id,
            supplier_id=item["supplier_id"],
            supplier_name=item["supplier_name"],
            quantity_mt=item["quantity_mt"],
            vessel_name=item["vessel_name"],
            imo_number=item["imo_number"],
            mmsi=item["mmsi"],
            origin_port=item["origin_port"],
            destination_port=config.destination_port,
            planned_eta=item["planned_eta"],
            current_eta=item["current_eta"],
            latest_eta=item["current_eta"],
            delay_days=item["delay_days"],
            delay_status=item["delay_status"],
            current_milestone=item["current_milestone"],
            current_location=item["current_location"],
            last_tracking_update_at=item["last_tracking_update_at"],
            eta_confidence=item["eta_confidence"],
            current_state=item["current_state"],
            source_of_truth="demo_coking_coal_story",
            latest_update_at=item["latest_update_at"],
        )
        db.add(shipment)
        flush_pending(db)
        db.add(
            ShipmentUpdate(
                tenant_id=tenant_id,
                shipment_id=shipment.id,
                source="demo_coking_coal_story",
                event_type="milestone_update",
                event_time=item["latest_update_at"],
                payload_json=None,
                notes=f"{shipment.shipment_id} seeded for the coking-coal pilot story.",
            )
        )

    seed_historical_validation_demo_incident(
        db,
        tenant_id=tenant_id,
        plant=plant,
        material=material,
        supplier=supplier,
        config=config,
        now=now,
    )


def seed_historical_validation_demo_incident(
    db: Session,
    *,
    tenant_id: int,
    plant: Plant,
    material: Material,
    supplier: Supplier,
    config: DemoMaterialConfig,
    now: datetime,
) -> None:
    incident_time = (now - timedelta(days=45)).replace(hour=9, minute=0, second=0)
    snapshot_time = incident_time - timedelta(days=10)
    db.add(
        StockSnapshot(
            tenant_id=tenant_id,
            plant_id=plant.id,
            material_id=material.id,
            on_hand_mt=Decimal("100"),
            quality_held_mt=Decimal("0"),
            available_to_consume_mt=Decimal("100"),
            daily_consumption_mt=Decimal("10"),
            snapshot_time=snapshot_time,
        )
    )
    historical_shipments = (
        {
            "shipment_id": "DEMO-HIST-COAL-DELAY-01",
            "quantity_mt": Decimal("80"),
            "planned_eta": incident_time - timedelta(days=1),
            "current_eta": incident_time + timedelta(days=2),
            "latest_update_at": incident_time - timedelta(days=6),
            "eta_confidence": Decimal("0.82"),
            "delay_days": 3,
            "delay_status": "delayed",
            "vessel_name": "MV Eastern Recovery",
            "origin_port": "Hay Point",
        },
        {
            "shipment_id": "DEMO-HIST-COAL-DELAY-02",
            "quantity_mt": Decimal("40"),
            "planned_eta": incident_time + timedelta(days=1),
            "current_eta": incident_time + timedelta(days=4),
            "latest_update_at": incident_time - timedelta(days=5, hours=4),
            "eta_confidence": Decimal("0.78"),
            "delay_days": 3,
            "delay_status": "delayed",
            "vessel_name": "MV Blast Furnace Relief",
            "origin_port": "Newcastle",
        },
    )
    for item in historical_shipments:
        db.add(
            Shipment(
                tenant_id=tenant_id,
                shipment_id=item["shipment_id"],
                plant_id=plant.id,
                material_id=material.id,
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                quantity_mt=item["quantity_mt"],
                vessel_name=item["vessel_name"],
                imo_number="9899001",
                mmsi="419100001",
                origin_port=item["origin_port"],
                destination_port=config.destination_port,
                planned_eta=item["planned_eta"],
                current_eta=item["current_eta"],
                latest_eta=item["current_eta"],
                delay_days=item["delay_days"],
                delay_status=item["delay_status"],
                current_milestone="ocean_transit_delay_confirmed",
                current_location="Indian Ocean",
                last_tracking_update_at=item["latest_update_at"],
                eta_confidence=item["eta_confidence"],
                current_state=ShipmentState.DELIVERED,
                source_of_truth="demo_historical_validation",
                latest_update_at=item["latest_update_at"],
            )
        )

    db.add(
        LineStopIncident(
            tenant_id=tenant_id,
            plant_id=plant.id,
            material_id=material.id,
            stopped_at=incident_time,
            duration_hours=Decimal("8"),
            notes=(
                "Coking Coal Continuity Incident - Material Continuity Failure. "
                "Operational impact: Blast Furnace Production Exposure."
            ),
        )
    )


def seed_onboarding_records(
    db: Session,
    *,
    tenant_id: int,
    admin_user_id: int,
    now: datetime,
) -> None:
    coking_story_shipments = 3
    standard_shipments_per_material = 4
    datasets = (
        (
            "shipments",
            "demo_inbound_shipments.csv",
            (len(DEMO_MATERIALS) - 1) * standard_shipments_per_material
            + coking_story_shipments,
        ),
        ("stock", "demo_stock_snapshots.csv", len(DEMO_MATERIALS)),
        ("thresholds", "demo_continuity_thresholds.csv", len(DEMO_MATERIALS)),
        ("operational_config", "demo_full_operational_config.csv", len(DEMO_MATERIALS)),
    )
    for index, (dataset_type, filename, record_count) in enumerate(datasets):
        uploaded = UploadedFile(
            tenant_id=tenant_id,
            original_filename=filename,
            storage_uri=f"demo://onboarding/{filename}",
            content_type="text/csv",
            file_size_bytes=record_count * 512,
            checksum_sha256=None,
            uploaded_by_user_id=admin_user_id,
            status="processed",
        )
        db.add(uploaded)
        flush_pending(db)
        completed_at = now - timedelta(minutes=20 - index)
        db.add(
            IngestionJob(
                tenant_id=tenant_id,
                uploaded_file_id=uploaded.id,
                source_type=dataset_type,
                status="completed",
                stage="completed",
                started_at=completed_at - timedelta(minutes=2),
                completed_at=completed_at,
                error_message=None,
                records_total=record_count,
                records_succeeded=record_count,
                records_failed=0,
                metadata_json={
                    "source": "demo_seed",
                    "tenant": "demo-steel",
                    "operationally_complete": True,
                },
            )
        )
        db.add(
            ExternalDataSource(
                tenant_id=tenant_id,
                source_type="demo_seed",
                source_url=f"demo://onboarding/{filename}",
                source_name=f"Demo Steel {dataset_type} onboarding feed",
                dataset_type=dataset_type,
                platform_detected="demo",
                mapping_config_json='{"mapping":"demo_complete"}',
                sync_frequency_minutes=1440,
                is_active=True,
                last_sync_status="success",
                last_synced_at=completed_at,
                last_error_message=None,
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
            flush_pending(db)
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
        admin_user = db.scalar(select(User).where(User.email == "admin@demo.opsdeck.local"))
        assert admin_user is not None
        reset_demo_operational_data(db, tenant.id)
        seed_full_demo_configuration(db, tenant.id, admin_user.id)
        db.commit()
        print(
            "Prepared demo-steel tenant with complete onboarding, operational configuration, "
            "stock, inbound, supplier, dependency, and trust demo data."
        )
        print("Demo password for tenant users: Password123!")
        print("Superadmin login: superadmin@opsdeck.local / SuperAdmin123! (no tenant membership)")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
