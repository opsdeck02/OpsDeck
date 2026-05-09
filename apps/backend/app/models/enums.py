from enum import StrEnum


class ShipmentState(StrEnum):
    PLANNED = "planned"
    IN_TRANSIT = "in_transit"
    AT_PORT = "at_port"
    DISCHARGING = "discharging"
    INLAND_TRANSIT = "inland_transit"
    DELIVERED = "delivered"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


class ExceptionSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExceptionType(StrEnum):
    ETA_RISK = "eta_risk"
    STOCKOUT_RISK = "stockout_risk"
    DEMURRAGE_RISK = "demurrage_risk"
    QUALITY_HOLD = "quality_hold"
    DOCUMENTATION_GAP = "documentation_gap"
    DATA_QUALITY = "data_quality"


class ExceptionStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class OperationalEventCategory(StrEnum):
    INVENTORY = "inventory"
    SHIPMENT = "shipment"
    SUPPLIER = "supplier"
    PLANNING = "planning"
    PRODUCTION = "production"
    DATA_QUALITY = "data_quality"
    MANUAL = "manual"
    SYSTEM = "system"


class OperationalEventType(StrEnum):
    INVENTORY_STOCK_UPDATED = "inventory_stock_updated"
    INVENTORY_BELOW_THRESHOLD_SIGNAL = "inventory_below_threshold_signal"
    INVENTORY_QUALITY_HOLD_UPDATED = "inventory_quality_hold_updated"
    SHIPMENT_ETA_CHANGED = "shipment_eta_changed"
    SHIPMENT_MILESTONE_UPDATED = "shipment_milestone_updated"
    SHIPMENT_DELAY_DETECTED = "shipment_delay_detected"
    SHIPMENT_LINKED_TO_PO = "shipment_linked_to_po"
    SUPPLIER_COMMITMENT_CHANGED = "supplier_commitment_changed"
    PLANNING_CONSUMPTION_UPDATED = "planning_consumption_updated"
    PRODUCTION_EXPOSURE_SIGNAL = "production_exposure_signal"
    DATA_SOURCE_SYNCED = "data_source_synced"
    DATA_SOURCE_STALE_SIGNAL = "data_source_stale_signal"
    MANUAL_OPERATIONAL_NOTE = "manual_operational_note"


class OperationalEventSourceType(StrEnum):
    MANUAL_UPLOAD = "manual_upload"
    EXTERNAL_DATA_SOURCE = "external_data_source"
    ERP = "erp"
    WMS = "wms"
    TMS = "tms"
    AIS = "ais"
    EMAIL_INGESTION = "email_ingestion"
    FILE_INGESTION = "file_ingestion"
    SUPPLIER_UPDATE = "supplier_update"
    SYSTEM = "system"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class OperationalEventFreshnessStatus(StrEnum):
    FRESH = "fresh"
    DELAYED = "delayed"
    STALE = "stale"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
