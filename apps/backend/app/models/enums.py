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

