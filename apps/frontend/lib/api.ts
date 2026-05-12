import { cookies } from "next/headers";

import type {
  CurrentUser,
  DashboardSnapshot,
  ExecutiveDashboardResponse,
  ExceptionDetailResponse,
  ExceptionListResponse,
  InlandMonitoringItem,
  MovementDetailResponse,
  MicrosoftConnection,
  MicrosoftDataSource,
  PilotReadinessResponse,
  PortMonitoringItem,
  Shipment,
  ShipmentDetailResponse,
  StockCoverDetailResponse,
  StockCoverSummaryResponse,
  Supplier,
  SupplierDetail,
  SupplierPerformanceSummary,
  TenantCreatePayload,
  TenantCreateResponse,
  TenantDetail,
  TenantPlanSummary,
  TenantSummary,
  TenantUser,
} from "@steelops/contracts";

import type { PlantContextOption } from "@/lib/plant-context";

const baseUrl =
  process.env.INTERNAL_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

export interface SignalRiskCandidate {
  risk_type: string;
  severity: string;
  plant_reference: string | null;
  material_reference: string | null;
  shipment_reference: string | null;
  supplier_reference: string | null;
  days_of_cover: string | null;
  projected_exhaustion_date: string | null;
  continuity_status: string | null;
  confidence_score: string | null;
  freshness_status: string | null;
  rule_reasons: string[];
  source_event_ids: number[];
  recommended_owner_role: string | null;
  explainability: SignalRiskExplainability | null;
}

export interface SignalRiskExplainability {
  summary: string;
  primary_driver: string;
  contributing_signals: Array<{
    signal_type: string;
    event_id: string | null;
    source_type: string | null;
    occurred_at: string | null;
    confidence_score: string | null;
    freshness_status: string | null;
    description: string;
  }>;
  operational_context: {
    plant_reference: string | null;
    material_reference: string | null;
    shipment_reference: string | null;
    supplier_reference: string | null;
    days_of_cover: string | null;
    projected_exhaustion_date: string | null;
    shipment_continuity_status: string | null;
  };
  trust_context: {
    lowest_confidence_score: string | null;
    worst_freshness_status: string | null;
    trust_warnings: string[];
  };
  reason_chain: string[];
}

export interface SignalExposureMapping {
  plant_reference: string | null;
  material_reference: string | null;
  shipment_reference: string | null;
  estimated_exposure_date: string | null;
  days_until_exposure: string | null;
  exposure_level: string;
  exposure_basis: string;
  operational_reason: string;
  trust_summary: SignalTrustSummary;
  related_risk_types: string[];
  timeline_event_count: number;
}

export interface SignalTrustSummary {
  lowest_confidence_score: string | null;
  worst_freshness_status: string | null;
  warnings: string[];
}

export interface SignalTimelineEntry {
  timestamp: string;
  event_type: string;
  event_category: string;
  title: string;
  description: string;
  plant_reference: string | null;
  material_reference: string | null;
  shipment_reference: string | null;
  supplier_reference: string | null;
  previous_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  confidence_score: string | null;
  freshness_status: string | null;
  source_type: string;
  source_reference: string | null;
  event_id: number;
}

export interface SignalRelationshipGraph {
  context: {
    tenant_id: number;
    plant_reference: string | null;
    material_reference: string | null;
    shipment_reference: string | null;
  };
  nodes: Array<{
    id: string;
    type: string;
    label: string;
    reference: string;
    metadata: Record<string, unknown>;
  }>;
  edges: Array<{
    from_node_id: string;
    to_node_id: string;
    relationship: string;
  }>;
  summary: {
    inventory_continuity: SignalInventoryContinuity | null;
    shipment_continuity: SignalShipmentContinuity | null;
    timeline_event_count: number;
    active_risk_candidate_count: number;
    confidence_summary: {
      lowest_confidence_score: string | null;
      worst_freshness_status: string | null;
    };
  };
}

export interface SignalInventoryContinuity {
  plant_reference: string;
  material_reference: string;
  on_hand_quantity: string;
  reserved_quantity: string;
  blocked_quantity: string;
  quality_hold_quantity: string;
  usable_quantity: string;
  inbound_committed_quantity: string;
  inbound_uncertain_quantity: string;
  daily_consumption_rate: string | null;
  days_of_cover: string | null;
  projected_exhaustion_date: string | null;
  unit: string;
  calculation_reasons: string[];
}

export interface SignalShipmentContinuity {
  shipment_reference: string;
  status: string;
  eta: string | null;
  previous_eta: string | null;
  eta_slip_days: string | null;
  current_milestone: string | null;
  missing_milestones: string[];
  overdue_milestones: string[];
  tracking_freshness_status: string;
  linked_purchase_order_reference: string | null;
  linked_material_reference: string | null;
  linked_plant_reference: string | null;
  continuity_reasons: string[];
}

export interface RiskWorkspaceResponse {
  selected_risk: SignalRiskCandidate | null;
  explainability: SignalRiskExplainability | null;
  exposure: SignalExposureMapping | null;
  timeline: {
    items: SignalTimelineEntry[];
    limit: number;
    offset: number;
    total: number;
  };
  context_graph: SignalRelationshipGraph | null;
  inventory_continuity: SignalInventoryContinuity[];
  shipment_continuity: SignalShipmentContinuity[];
  trust_summary: SignalTrustSummary | null;
  empty: boolean;
}

export async function getRiskWorkspace(params?: {
  risk_type?: string;
  plant_reference?: string;
  material_reference?: string;
  shipment_reference?: string;
  severity?: string;
  timeline_limit?: number;
  timeline_offset?: number;
}): Promise<RiskWorkspaceResponse | null> {
  const query = new URLSearchParams();
  if (params?.risk_type) query.set("risk_type", params.risk_type);
  if (params?.plant_reference)
    query.set("plant_reference", params.plant_reference);
  if (params?.material_reference)
    query.set("material_reference", params.material_reference);
  if (params?.shipment_reference)
    query.set("shipment_reference", params.shipment_reference);
  if (params?.severity) query.set("severity", params.severity);
  if (params?.timeline_limit !== undefined) {
    query.set("timeline_limit", String(params.timeline_limit));
  }
  if (params?.timeline_offset !== undefined) {
    query.set("timeline_offset", String(params.timeline_offset));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return getAuthenticatedJson<RiskWorkspaceResponse>(
    `/api/v1/signal-engine/risk-workspace${suffix}`,
  );
}

export async function getSignalRisks(params?: {
  risk_type?: string;
  plant_reference?: string;
  material_reference?: string;
  shipment_reference?: string;
  severity?: string;
}): Promise<SignalRiskCandidate[]> {
  const query = new URLSearchParams();
  if (params?.risk_type) query.set("risk_type", params.risk_type);
  if (params?.plant_reference)
    query.set("plant_reference", params.plant_reference);
  if (params?.material_reference)
    query.set("material_reference", params.material_reference);
  if (params?.shipment_reference)
    query.set("shipment_reference", params.shipment_reference);
  if (params?.severity) query.set("severity", params.severity);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return (
    (await getAuthenticatedJson<SignalRiskCandidate[]>(
      `/api/v1/signal-engine/risks${suffix}`,
    )) ?? []
  );
}

export async function getDashboardSnapshot(): Promise<DashboardSnapshot | null> {
  return getAuthenticatedJson<DashboardSnapshot>("/api/v1/dashboard/snapshot");
}

export async function getExecutiveDashboard(): Promise<ExecutiveDashboardResponse | null> {
  return getAuthenticatedJson<ExecutiveDashboardResponse>(
    "/api/v1/dashboard/executive",
  );
}

export async function getCurrentUser(): Promise<CurrentUser | null> {
  return getAuthenticatedJson<CurrentUser>("/api/v1/auth/me");
}

export async function getPilotReadiness(): Promise<PilotReadinessResponse | null> {
  return getAuthenticatedJson<PilotReadinessResponse>(
    "/api/v1/dashboard/pilot-readiness",
  );
}

export async function getTenantPlan(): Promise<TenantPlanSummary | null> {
  return getAuthenticatedJson<TenantPlanSummary>("/api/v1/tenants/plan");
}

export async function getShipments(params?: {
  plant_id?: number;
  material_id?: number;
  state?: string;
  search?: string;
}): Promise<Shipment[]> {
  const query = new URLSearchParams();
  if (params?.plant_id) query.set("plant_id", String(params.plant_id));
  if (params?.material_id) query.set("material_id", String(params.material_id));
  if (params?.state) query.set("state", params.state);
  if (params?.search) query.set("search", params.search);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return (
    (await getAuthenticatedJson<Shipment[]>(
      `/api/v1/shipments/visibility${suffix}`,
    )) ?? []
  );
}

export async function getShipmentDetail(
  shipmentId: string,
): Promise<ShipmentDetailResponse | null> {
  return getAuthenticatedJson<ShipmentDetailResponse>(
    `/api/v1/shipments/${shipmentId}`,
  );
}

export async function getMovementDetail(
  shipmentId: string,
): Promise<MovementDetailResponse | null> {
  return getAuthenticatedJson<MovementDetailResponse>(
    `/api/v1/shipments/${shipmentId}/movement`,
  );
}

export async function getPortMonitoring(params?: {
  plant_id?: number;
  material_id?: number;
  shipment_id?: string;
  confidence?: string;
  delayed_only?: boolean;
}): Promise<PortMonitoringItem[]> {
  const query = new URLSearchParams();
  if (params?.plant_id) query.set("plant_id", String(params.plant_id));
  if (params?.material_id) query.set("material_id", String(params.material_id));
  if (params?.shipment_id) query.set("shipment_id", params.shipment_id);
  if (params?.confidence) query.set("confidence", params.confidence);
  if (params?.delayed_only) query.set("delayed_only", "true");
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return (
    (await getAuthenticatedJson<PortMonitoringItem[]>(
      `/api/v1/shipments/port-monitoring${suffix}`,
    )) ?? []
  );
}

export async function getInlandMonitoring(params?: {
  plant_id?: number;
  material_id?: number;
  shipment_id?: string;
  confidence?: string;
  delayed_only?: boolean;
}): Promise<InlandMonitoringItem[]> {
  const query = new URLSearchParams();
  if (params?.plant_id) query.set("plant_id", String(params.plant_id));
  if (params?.material_id) query.set("material_id", String(params.material_id));
  if (params?.shipment_id) query.set("shipment_id", params.shipment_id);
  if (params?.confidence) query.set("confidence", params.confidence);
  if (params?.delayed_only) query.set("delayed_only", "true");
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return (
    (await getAuthenticatedJson<InlandMonitoringItem[]>(
      `/api/v1/shipments/inland-monitoring${suffix}`,
    )) ?? []
  );
}

export async function getStockCoverSummary(): Promise<StockCoverSummaryResponse | null> {
  return getAuthenticatedJson<StockCoverSummaryResponse>("/api/v1/stock/cover");
}

export async function getPlantContextOptions(): Promise<PlantContextOption[]> {
  const [stockSummary, risks] = await Promise.all([
    getStockCoverSummary(),
    getSignalRisks(),
  ]);
  const options = new Map<string, PlantContextOption>();

  for (const row of stockSummary?.rows ?? []) {
    if (!row.plant_code) continue;
    options.set(row.plant_code, {
      reference: row.plant_code,
      label: row.plant_name || row.plant_code,
      plantId: row.plant_id,
    });
  }

  for (const risk of risks) {
    if (!risk.plant_reference || options.has(risk.plant_reference)) continue;
    options.set(risk.plant_reference, {
      reference: risk.plant_reference,
      label: risk.plant_reference,
    });
  }

  return [...options.values()].sort((left, right) =>
    left.label.localeCompare(right.label),
  );
}

export async function getStockCoverDetail(
  plantId: number,
  materialId: number,
): Promise<StockCoverDetailResponse | null> {
  return getAuthenticatedJson<StockCoverDetailResponse>(
    `/api/v1/stock/cover/${plantId}/${materialId}`,
  );
}

export async function getSuppliers(): Promise<Supplier[]> {
  return (await getAuthenticatedJson<Supplier[]>("/api/v1/suppliers")) ?? [];
}

export async function getSupplierDetail(
  supplierId: string,
): Promise<SupplierDetail | null> {
  return getAuthenticatedJson<SupplierDetail>(
    `/api/v1/suppliers/${supplierId}`,
  );
}

export async function getSupplierPerformanceSummary(): Promise<SupplierPerformanceSummary | null> {
  return getAuthenticatedJson<SupplierPerformanceSummary>(
    "/api/v1/suppliers/performance/summary",
  );
}

export async function getMicrosoftConnections(): Promise<
  MicrosoftConnection[]
> {
  return (
    (await getAuthenticatedJson<MicrosoftConnection[]>(
      "/api/v1/microsoft/connections",
    )) ?? []
  );
}

export async function getMicrosoftDataSources(): Promise<
  MicrosoftDataSource[]
> {
  return (
    (await getAuthenticatedJson<MicrosoftDataSource[]>(
      "/api/v1/microsoft/data-sources",
    )) ?? []
  );
}

export async function getExceptions(params?: {
  status?: string;
  severity?: string;
  type?: string;
  plant_id?: number;
  material_id?: number;
  shipment_id?: string;
  owner_user_id?: number;
  unassigned_only?: boolean;
}): Promise<ExceptionListResponse | null> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.severity) query.set("severity", params.severity);
  if (params?.type) query.set("type", params.type);
  if (params?.plant_id) query.set("plant_id", String(params.plant_id));
  if (params?.material_id) query.set("material_id", String(params.material_id));
  if (params?.shipment_id) query.set("shipment_id", params.shipment_id);
  if (params?.owner_user_id)
    query.set("owner_user_id", String(params.owner_user_id));
  if (params?.unassigned_only) query.set("unassigned_only", "true");
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return getAuthenticatedJson<ExceptionListResponse>(
    `/api/v1/exceptions${suffix}`,
  );
}

export async function getExceptionDetail(
  exceptionId: number,
): Promise<ExceptionDetailResponse | null> {
  return getAuthenticatedJson<ExceptionDetailResponse>(
    `/api/v1/exceptions/${exceptionId}`,
  );
}

export async function getTenantUsers(): Promise<TenantUser[]> {
  return (await getAuthenticatedJson<TenantUser[]>("/api/v1/users")) ?? [];
}

export async function getUserProfile(
  userId: number,
): Promise<TenantUser | null> {
  return getAuthenticatedJson<TenantUser>(`/api/v1/users/${userId}`);
}

export async function getAllTenants(): Promise<TenantSummary[]> {
  return (
    (await getAuthenticatedJson<TenantSummary[]>(
      "/api/v1/tenants/admin/all",
    )) ?? []
  );
}

export async function getSuperadminTenantUsers(
  tenantId: number,
): Promise<TenantUser[]> {
  return (
    (await getAuthenticatedJson<TenantUser[]>(
      `/api/v1/users/admin/tenant/${tenantId}`,
    )) ?? []
  );
}

export async function getTenantDetails(
  tenantId: number,
): Promise<TenantDetail | null> {
  return getAuthenticatedJson<TenantDetail>(
    `/api/v1/tenants/admin/${tenantId}`,
  );
}

export async function createTenant(
  payload: TenantCreatePayload,
): Promise<TenantCreateResponse | null> {
  const cookieStore = cookies();
  const token = cookieStore.get("__Host-opsdeck-session")?.value;
  if (!token) return null;

  try {
    const response = await fetch(`${baseUrl}/api/v1/tenants/admin`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) return null;
    return (await response.json()) as TenantCreateResponse;
  } catch {
    return null;
  }
}

export async function activateTenant(tenantId: number): Promise<{
  id: number;
  name: string;
  slug: string;
  is_active: boolean;
} | null> {
  const cookieStore = cookies();
  const token = cookieStore.get("__Host-opsdeck-session")?.value;
  if (!token) return null;

  try {
    const response = await fetch(
      `${baseUrl}/api/v1/tenants/admin/${tenantId}/activate`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      },
    );

    if (!response.ok) return null;
    return (await response.json()) as {
      id: number;
      name: string;
      slug: string;
      is_active: boolean;
    };
  } catch {
    return null;
  }
}

export async function deactivateTenant(tenantId: number): Promise<{
  id: number;
  name: string;
  slug: string;
  is_active: boolean;
} | null> {
  const cookieStore = cookies();
  const token = cookieStore.get("__Host-opsdeck-session")?.value;
  if (!token) return null;

  try {
    const response = await fetch(
      `${baseUrl}/api/v1/tenants/admin/${tenantId}/deactivate`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      },
    );

    if (!response.ok) return null;
    return (await response.json()) as {
      id: number;
      name: string;
      slug: string;
      is_active: boolean;
    };
  } catch {
    return null;
  }
}

export async function deleteTenant(tenantId: number): Promise<boolean> {
  const cookieStore = cookies();
  const token = cookieStore.get("__Host-opsdeck-session")?.value;
  if (!token) return false;

  try {
    const response = await fetch(
      `${baseUrl}/api/v1/tenants/admin/${tenantId}`,
      {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      },
    );

    return response.ok;
  } catch {
    return false;
  }
}

async function getAuthenticatedJson<T>(path: string): Promise<T | null> {
  const cookieStore = cookies();
  const token = cookieStore.get("__Host-opsdeck-session")?.value;
  const tenantSlug = cookieStore.get("steelops_tenant")?.value;

  if (!token) {
    return null;
  }

  try {
    const response = await fetch(`${baseUrl}${path}`, {
      cache: "no-store",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
      },
    });

    if (!response.ok) {
      return null;
    }

    return (await response.json()) as T;
  } catch {
    return null;
  }
}
