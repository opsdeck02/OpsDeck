export interface DashboardMetric {
  label: string;
  value: string;
  trend: string;
}

export interface DashboardSnapshot {
  tenant: string;
  metrics: DashboardMetric[];
  critical_risks: number;
  warnings: number;
  insufficient_data: number;
}

export interface DashboardFreshness {
  last_updated_at: string | null;
  freshness_label: string;
}

export interface LastSyncSummary {
  last_synced_at: string | null;
  last_sync_status: string | null;
  new_critical_risks_count: number;
  resolved_risks_count: number;
  newly_breached_actions_count: number;
}

export interface AutomatedDataFreshness {
  last_sync_summary: LastSyncSummary;
  data_freshness_status: string;
  data_freshness_age_minutes: number | null;
}

export interface ExecutiveKpis {
  tracked_combinations: number;
  critical_risks: number;
  warning_risks: number;
  open_exceptions: number;
  unassigned_exceptions: number;
  total_estimated_value_at_risk: string;
}

export interface ExecutiveRiskItem {
  plant_id: number;
  plant_name: string;
  material_id: number;
  material_name: string;
  days_of_cover: string | null;
  threshold_days: string | null;
  status: string;
  confidence: string;
  raw_inbound_pipeline_mt: string;
  effective_inbound_pipeline_mt: string;
  inbound_protection_indicator: string;
  risk_hours_remaining: string | null;
  estimated_production_exposure_mt: string | null;
  estimated_value_at_risk: string | null;
  value_per_mt_used: string | null;
  criticality_multiplier_used: string | null;
  urgency_band: "immediate" | "next_24h" | "next_72h" | "monitor";
  recommended_action_code: string | null;
  recommended_action_text: string | null;
  owner_role_recommended: string | null;
  action_deadline_hours: number | null;
  action_priority: string | null;
  action_status: string | null;
  action_sla_breach: boolean;
  action_age_hours: string | null;
}

export interface ExecutiveExceptionItem {
  id: number;
  title: string;
  severity: string;
  status: string;
  owner_name: string | null;
  updated_at: string;
  recommended_next_step: string | null;
}

export interface ExecutiveMovementItem {
  shipment_id: string;
  plant_name: string;
  material_name: string;
  confidence: string;
  freshness_label: string;
  issue_label: string;
}

export interface SupplierPerformanceItem {
  supplier_name: string;
  total_shipments: number;
  on_time_shipments: number;
  on_time_reliability_pct: string;
  active_shipments: number;
  active_shipments_with_risk_signal: number;
  risk_signal_pct: string;
}

export interface ExecutiveSupplierSummaryItem {
  supplier_id: string;
  supplier_name: string;
  reliability_grade: string;
  on_time_reliability_pct: string;
  risk_signal_pct: string;
  active_shipments: number;
}

export interface ExecutiveSupplierPerformanceSummary {
  top_suppliers: ExecutiveSupplierSummaryItem[];
  bottom_suppliers: ExecutiveSupplierSummaryItem[];
  grade_d_count: number;
  high_risk_supplier_count: number;
}

export interface AttentionItem {
  kind: string;
  description: string;
  linked_label: string;
  href: string;
  current_owner: string | null;
  recommended_next_step: string;
  owner_role_recommended: string | null;
  action_deadline_hours: number | null;
  action_priority: string | null;
  action_status: string | null;
  action_sla_breach: boolean;
  action_age_hours: string | null;
}

export interface ExecutiveDashboardResponse {
  tenant: string;
  kpis: ExecutiveKpis;
  automated_data_freshness: AutomatedDataFreshness | null;
  stock_freshness: DashboardFreshness;
  exception_freshness: DashboardFreshness;
  movement_freshness: DashboardFreshness;
  top_risks: ExecutiveRiskItem[];
  critical_open_exceptions: ExecutiveExceptionItem[];
  unassigned_exceptions: ExecutiveExceptionItem[];
  recently_updated_exceptions: ExecutiveExceptionItem[];
  stale_movement_shipments: ExecutiveMovementItem[];
  low_confidence_shipments: ExecutiveMovementItem[];
  likely_delayed_shipments: ExecutiveMovementItem[];
  supplier_performance: SupplierPerformanceItem[];
  supplier_performance_summary: ExecutiveSupplierPerformanceSummary;
  needs_attention: AttentionItem[];
}

export interface SupplierPerformance {
  total_shipments: number;
  active_shipments: number;
  on_time_reliability_pct: string;
  avg_eta_drift_hours: string;
  risk_signal_pct: string;
  total_value_at_risk: string;
  materials_supplied: string[];
  ports_used: string[];
  last_shipment_date: string | null;
  reliability_grade: string;
}

export interface Supplier {
  id: string;
  tenant_id: number;
  name: string;
  code: string;
  primary_port: string | null;
  secondary_ports: string[] | null;
  material_categories: string[] | null;
  country_of_origin: string | null;
  contact_name: string | null;
  contact_email: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  performance: SupplierPerformance;
}

export interface SupplierDetail extends Supplier {
  linked_shipments: Shipment[];
}

export interface SupplierPerformanceSummary {
  top_suppliers: Supplier[];
  bottom_suppliers: Supplier[];
  grade_d_count: number;
  high_risk_supplier_count: number;
}

export interface SupplierPayload {
  name: string;
  code: string;
  primary_port?: string | null;
  secondary_ports?: string[] | null;
  material_categories?: string[] | null;
  country_of_origin?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  is_active?: boolean;
}

export interface PilotReadinessCheck {
  key: string;
  label: string;
  ready: boolean;
  detail: string;
  last_updated_at: string | null;
}

export interface PilotReadinessCounts {
  uploaded_files: number;
  ingestion_jobs: number;
  stock_cover_rows: number;
  open_exceptions: number;
  stale_signals: number;
}

export interface PilotReadinessResponse {
  tenant: string;
  counts: PilotReadinessCounts;
  last_upload_at: string | null;
  last_stock_update_at: string | null;
  last_exception_update_at: string | null;
  last_movement_update_at: string | null;
  checks: PilotReadinessCheck[];
}

export interface TenantSummary {
  id: number;
  name: string;
  slug: string;
  plan_tier: "pilot" | "paid" | "enterprise";
  max_users: number | null;
  is_active: boolean;
  access_weeks: number | null;
  access_expires_at: string | null;
  active_user_count: number | null;
  created_at: string;
}

export interface TenantDetail {
  id: number;
  name: string;
  slug: string;
  plan_tier: "pilot" | "paid" | "enterprise";
  max_users: number | null;
  is_active: boolean;
  access_weeks: number | null;
  access_expires_at: string | null;
  active_user_count: number;
  created_at: string;
  users: TenantUser[];
  capabilities: Record<string, boolean>;
}

export interface TenantCreatePayload {
  name: string;
  slug: string;
  plan_tier?: "pilot" | "paid" | "enterprise";
  max_users: number | null;
  access_weeks?: number | null;
  admin_user?: {
    email: string;
    full_name: string;
    password: string;
  } | null;
}

export type RoleName =
  | "tenant_admin"
  | "buyer_user"
  | "logistics_user"
  | "planner_user"
  | "management_user"
  | "sponsor_user";

export interface TenantMembership {
  tenant_id: number;
  tenant_name: string;
  tenant_slug: string;
  role: RoleName;
}

export interface CurrentUser {
  id: number;
  email: string;
  full_name: string;
  is_superadmin: boolean;
  memberships: TenantMembership[];
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  user: CurrentUser;
}

export interface Shipment {
  id: number;
  shipment_id: string;
  material_id: number;
  plant_id: number;
  supplier_name: string;
  quantity_mt: string;
  vessel_name: string | null;
  plant_name: string;
  material_name: string;
  origin_port: string | null;
  destination_port: string | null;
  planned_eta: string;
  current_eta: string;
  shipment_state: string;
  confidence: string;
  latest_status_source: string;
  last_update_at: string;
  contributing_data_sources: string[];
  contribution_band: string;
}

export interface RowValidationError {
  row_number: number;
  errors: string[];
}

export interface IngestionSummary {
  created: number;
  updated: number;
  unchanged: number;
}

export interface UploadResult {
  upload_id: number;
  ingestion_job_id: number;
  file_type: string;
  rows_received: number;
  rows_accepted: number;
  rows_rejected: number;
  validation_errors: RowValidationError[];
  summary_counts: IngestionSummary;
  platform_detected: string | null;
  transformed_url: string | null;
}

export interface IngestionJob {
  id: number;
  upload_id: number | null;
  file_type: string;
  status: string;
  rows_received: number;
  rows_accepted: number;
  rows_rejected: number;
  error_message: string | null;
}

export interface HeaderMappingSuggestion {
  source_header: string;
  suggested_field: string | null;
  confidence: string;
  alternatives: string[];
}

export interface MappingPreview {
  file_type: string;
  headers: string[];
  required_fields: string[];
  optional_fields: string[];
  suggestions: HeaderMappingSuggestion[];
  platform_detected: string | null;
  transformed_url: string | null;
}

export interface StockCoverBreakdown {
  current_stock_mt: string | null;
  inbound_pipeline_mt: string;
  raw_inbound_pipeline_mt: string;
  effective_inbound_pipeline_mt: string;
  total_considered_mt: string | null;
  daily_consumption_mt: string | null;
  days_of_cover: string | null;
  threshold_days: string | null;
  warning_days: string | null;
  status: "safe" | "warning" | "critical" | "insufficient_data";
  estimated_breach_date: string | null;
  confidence_level: "high" | "medium" | "low";
  insufficient_data_reason: string | null;
  data_freshness_hours: string | null;
  linked_shipment_count: number;
  weighted_shipment_count: string;
  risk_hours_remaining: string | null;
  estimated_production_exposure_mt: string | null;
  estimated_value_at_risk: string | null;
  value_per_mt_used: string | null;
  criticality_multiplier_used: string | null;
  urgency_band: "immediate" | "next_24h" | "next_72h" | "monitor";
  recommended_action_code: string | null;
  recommended_action_text: string | null;
  owner_role_recommended: string | null;
  action_deadline_hours: number | null;
  action_priority: string | null;
  action_status: string | null;
  action_sla_breach: boolean;
  action_age_hours: string | null;
}

export interface StockCoverRow {
  plant_id: number;
  plant_code: string;
  plant_name: string;
  material_id: number;
  material_code: string;
  material_name: string;
  latest_snapshot_time: string | null;
  calculation: StockCoverBreakdown;
}

export interface StockCoverSummaryResponse {
  total_combinations: number;
  critical_risks: number;
  warnings: number;
  insufficient_data: number;
  rows: StockCoverRow[];
}

export interface ShipmentContribution {
  id: number;
  shipment_id: string;
  supplier_name: string;
  raw_quantity_mt: string;
  effective_quantity_mt: string;
  contribution_factor: string;
  current_eta: string;
  current_state: string;
  shipment_state: string;
  confidence: string;
  freshness_label: string;
  explanation: string;
}

export interface ShipmentUpdateEvent {
  source: string;
  event_type: string;
  event_time: string;
  notes: string | null;
}

export interface PortEvent {
  berth_status: string;
  waiting_days: string;
  discharge_started_at: string | null;
  discharge_rate_mt_per_day: string | null;
  estimated_demurrage_exposure: string | null;
  updated_at: string;
}

export interface InlandMovement {
  mode: string;
  carrier_name: string | null;
  origin_location: string | null;
  destination_location: string | null;
  planned_departure_at: string | null;
  planned_arrival_at: string | null;
  actual_departure_at: string | null;
  actual_arrival_at: string | null;
  current_state: string;
  updated_at: string;
}

export interface FreshnessInfo {
  last_updated_at: string | null;
  freshness_hours: string | null;
  freshness_label: "fresh" | "aging" | "stale" | "unknown";
}

export interface PortMonitoringItem {
  shipment_id: string;
  plant_id: number;
  plant_name: string;
  material_id: number;
  material_name: string;
  port_status: string;
  latest_berth_state: string;
  waiting_time_days: string;
  latest_discharge_timestamp: string | null;
  likely_port_delay: boolean;
  stale_record: boolean;
  missing_supporting_signal: boolean;
  freshness: FreshnessInfo;
  confidence: "high" | "medium" | "low";
  confidence_reasons: string[];
}

export interface InlandMonitoringItem {
  shipment_id: string;
  plant_id: number;
  plant_name: string;
  material_id: number;
  material_name: string;
  dispatch_status: string;
  transporter_name: string | null;
  expected_arrival: string | null;
  actual_arrival: string | null;
  inland_delay_flag: boolean;
  stale_record: boolean;
  missing_supporting_signal: boolean;
  freshness: FreshnessInfo;
  confidence: "high" | "medium" | "low";
  confidence_reasons: string[];
}

export interface ShipmentDetailResponse {
  shipment: Shipment;
  supplier_name: string;
  imo_number: string | null;
  mmsi: string | null;
  eta_confidence: string | null;
  source_of_truth: string;
  confidence_reasons: string[];
  fallback_notes: string[];
  updates: ShipmentUpdateEvent[];
  port_events: PortEvent[];
  inland_movements: InlandMovement[];
  port_summary: PortMonitoringItem | null;
  inland_summary: InlandMonitoringItem | null;
  movement_gaps: string[];
  movement_notes: string[];
}

export interface StockCoverDetailResponse {
  row: StockCoverRow;
  shipments: ShipmentContribution[];
  confidence_reasons: string[];
  assumptions: string[];
  impact_explanation: string[];
  recommendation_why: string[];
  current_owner: string | null;
}

export interface MovementDetailResponse {
  shipment: Shipment;
  port_summary: PortMonitoringItem | null;
  inland_summary: InlandMonitoringItem | null;
  overall_confidence: "high" | "medium" | "low";
  overall_freshness: FreshnessInfo;
  missing_signals: string[];
  progress_notes: string[];
}

export type ExceptionSeverity = "low" | "medium" | "high" | "critical";
export type ExceptionStatus = "open" | "in_progress" | "resolved" | "closed";
export type ExceptionType =
  | "stock_cover_critical"
  | "stock_cover_warning"
  | "shipment_eta_delay"
  | "shipment_stale_update"
  | "inland_delay_risk";

export interface ExceptionLinkedEntity {
  id: number;
  label: string;
}

export interface ExceptionOwner {
  id: number;
  full_name: string;
  email: string;
  role: RoleName | null;
}

export interface ExceptionComment {
  id: number;
  author: ExceptionOwner | null;
  comment: string;
  created_at: string;
}

export interface ExceptionItem {
  id: number;
  tenant_id: number;
  type: ExceptionType;
  severity: ExceptionSeverity;
  status: ExceptionStatus;
  title: string;
  summary: string | null;
  trigger_source: ExceptionType;
  linked_shipment: ExceptionLinkedEntity | null;
  linked_plant: ExceptionLinkedEntity | null;
  linked_material: ExceptionLinkedEntity | null;
  current_owner: ExceptionOwner | null;
  created_at: string;
  updated_at: string;
  triggered_at: string;
  due_at: string | null;
  recommended_next_step: string | null;
  action_status: string;
  action_started_at: string | null;
  action_completed_at: string | null;
  action_sla_breach: boolean;
  action_age_hours: string | null;
}

export interface ExceptionCounts {
  open_exceptions: number;
  critical_exceptions: number;
  unassigned_exceptions: number;
  resolved_recently: number;
}

export interface ExceptionListResponse {
  counts: ExceptionCounts;
  items: ExceptionItem[];
}

export interface ExceptionDetailResponse {
  exception: ExceptionItem;
  linked_shipment_detail: {
    shipment_id: string;
    shipment_state: string;
    confidence: string;
    last_update_at: string;
    latest_status_source: string;
    contribution_band: string;
  } | null;
  linked_context_notes: string[];
  comments: ExceptionComment[];
  status_options: ExceptionStatus[];
}

export interface ExceptionEvaluationResponse {
  created: number;
  updated: number;
  resolved: number;
  open_after_evaluation: number;
}

export interface TenantUser {
  id: number;
  email: string;
  full_name: string;
  role: RoleName;
  is_active?: boolean;
  is_superadmin?: boolean;
  tenant_id?: number;
  tenant_name?: string;
  tenant_slug?: string;
  created_at?: string;
}

export interface TenantCreatePayload {
  name: string;
  slug: string;
  max_users: number | null;
  admin_user?: {
    email: string;
    full_name: string;
    password: string;
  } | null;
}

export interface TenantCreateResponse {
  id: number;
  name: string;
  slug: string;
  plan_tier: "pilot" | "paid" | "enterprise";
  max_users: number | null;
  created_at: string;
  admin_user: TenantUser | null;
}

export interface TenantPlanSummary {
  tenant_id: number;
  tenant_name: string;
  tenant_slug: string;
  plan_tier: "pilot" | "paid" | "enterprise";
  capabilities: Record<string, boolean>;
}

export interface ExternalDataSource {
  id: number;
  tenant_id: number;
  source_type: "google_sheets" | "excel_online";
  source_url: string;
  source_name: string;
  dataset_type: "shipments" | "stock" | "thresholds";
  platform_detected: string | null;
  mapping_config: Record<string, unknown>;
  sync_frequency_minutes: number;
  is_active: boolean;
  last_sync_status: string | null;
  last_synced_at: string | null;
  last_error_message: string | null;
  data_freshness_status: string;
  data_freshness_age_minutes: number | null;
  last_sync_summary: LastSyncSummary;
  created_at: string;
  updated_at: string;
}

export interface ExternalDataSourceSyncResult {
  source_id: number;
  sync_status: string;
  rows_received: number;
  rows_accepted: number;
  rows_rejected: number;
  validation_summary: {
    created: number;
    updated: number;
    unchanged: number;
  };
  validation_errors: Array<{
    row_number: number;
    errors: string[];
  }>;
  last_error: string | null;
  last_synced_at: string | null;
  new_critical_risks_count: number;
  resolved_risks_count: number;
  newly_breached_actions_count: number;
  data_freshness_status: string;
  data_freshness_age_minutes: number | null;
}

export interface TenantUserCreatePayload {
  email: string;
  full_name: string;
  password: string;
  role: RoleName;
  tenant_id?: number | null;
}

export const dashboardSeedMetrics: DashboardMetric[] = [
  {
    label: "Expected Receipts",
    value: "14",
    trend: "+2 vs yesterday",
  },
  {
    label: "At-Risk ETA",
    value: "3",
    trend: "-1 after morning sync",
  },
  {
    label: "Yard Capacity",
    value: "72%",
    trend: "+4%",
  },
  {
    label: "Rule Breaches",
    value: "5",
    trend: "1 escalated in last hour",
  },
];
