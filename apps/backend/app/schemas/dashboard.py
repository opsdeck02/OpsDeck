from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class DashboardMetric(BaseModel):
    label: str
    value: str
    trend: str


class DashboardSnapshot(BaseModel):
    tenant: str
    metrics: list[DashboardMetric]
    critical_risks: int
    warnings: int
    insufficient_data: int


class DashboardFreshness(BaseModel):
    last_updated_at: datetime | None
    freshness_label: str


class LastSyncSummary(BaseModel):
    last_synced_at: datetime | None
    last_sync_status: str | None
    new_critical_risks_count: int
    resolved_risks_count: int
    newly_breached_actions_count: int
    source_type: str | None = None


class AutomatedDataFreshness(BaseModel):
    last_sync_summary: LastSyncSummary
    data_freshness_status: str
    data_freshness_age_minutes: int | None


class ExecutiveKpis(BaseModel):
    tracked_combinations: int
    critical_risks: int
    warning_risks: int
    open_exceptions: int
    unassigned_exceptions: int
    total_estimated_value_at_risk: Decimal


class ExecutiveRiskItem(BaseModel):
    plant_id: int
    plant_name: str
    material_id: int
    material_name: str
    days_of_cover: Decimal | None
    threshold_days: Decimal | None
    status: str
    confidence: str
    current_stock_mt: Decimal | None
    usable_stock_mt: Decimal | None
    blocked_stock_mt: Decimal | None
    next_inbound_eta: datetime | None
    raw_inbound_pipeline_mt: Decimal
    effective_inbound_pipeline_mt: Decimal
    inbound_protection_indicator: str
    risk_hours_remaining: Decimal | None
    estimated_production_exposure_mt: Decimal | None
    estimated_value_at_risk: Decimal | None
    value_per_mt_used: Decimal | None
    criticality_multiplier_used: Decimal | None
    urgency_band: str
    recommended_action_code: str | None
    recommended_action_text: str | None
    owner_role_recommended: str | None
    action_deadline_hours: int | None
    action_priority: str | None
    action_status: str | None
    action_sla_breach: bool
    action_age_hours: Decimal | None


class ExecutiveExceptionItem(BaseModel):
    id: int
    title: str
    severity: str
    status: str
    owner_name: str | None
    updated_at: datetime
    recommended_next_step: str | None


class ExecutiveMovementItem(BaseModel):
    shipment_id: str
    plant_name: str
    material_name: str
    confidence: str
    freshness_label: str
    issue_label: str


class SupplierPerformanceItem(BaseModel):
    supplier_name: str
    total_shipments: int
    on_time_shipments: int
    on_time_reliability_pct: Decimal
    active_shipments: int
    active_shipments_with_risk_signal: int
    risk_signal_pct: Decimal


class ExecutiveSupplierSummaryItem(BaseModel):
    supplier_id: UUID
    supplier_name: str
    reliability_grade: str
    on_time_reliability_pct: Decimal
    risk_signal_pct: Decimal
    active_shipments: int


class ExecutiveSupplierPerformanceSummary(BaseModel):
    top_suppliers: list[ExecutiveSupplierSummaryItem]
    bottom_suppliers: list[ExecutiveSupplierSummaryItem]
    grade_d_count: int
    high_risk_supplier_count: int


class AttentionItem(BaseModel):
    kind: str
    description: str
    linked_label: str
    href: str
    current_owner: str | None
    recommended_next_step: str
    owner_role_recommended: str | None
    action_deadline_hours: int | None
    action_priority: str | None
    action_status: str | None
    action_sla_breach: bool
    action_age_hours: Decimal | None


class ExecutiveDashboardResponse(BaseModel):
    tenant: str
    kpis: ExecutiveKpis
    automated_data_freshness: AutomatedDataFreshness | None = None
    stock_freshness: DashboardFreshness
    exception_freshness: DashboardFreshness
    movement_freshness: DashboardFreshness
    top_risks: list[ExecutiveRiskItem]
    critical_open_exceptions: list[ExecutiveExceptionItem]
    unassigned_exceptions: list[ExecutiveExceptionItem]
    recently_updated_exceptions: list[ExecutiveExceptionItem]
    stale_movement_shipments: list[ExecutiveMovementItem]
    low_confidence_shipments: list[ExecutiveMovementItem]
    likely_delayed_shipments: list[ExecutiveMovementItem]
    supplier_performance: list[SupplierPerformanceItem]
    supplier_performance_summary: ExecutiveSupplierPerformanceSummary
    needs_attention: list[AttentionItem]


class PilotReadinessCheck(BaseModel):
    key: str
    label: str
    ready: bool
    detail: str
    last_updated_at: datetime | None


class PilotReadinessCounts(BaseModel):
    uploaded_files: int
    ingestion_jobs: int
    stock_cover_rows: int
    open_exceptions: int
    stale_signals: int


class PilotReadinessResponse(BaseModel):
    tenant: str
    counts: PilotReadinessCounts
    last_upload_at: datetime | None
    last_stock_update_at: datetime | None
    last_exception_update_at: datetime | None
    last_movement_update_at: datetime | None
    checks: list[PilotReadinessCheck]
