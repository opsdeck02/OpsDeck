import { cookies } from "next/headers";

import type {
  CurrentUser,
  DashboardSnapshot,
  ExecutiveDashboardResponse,
  ExceptionDetailResponse,
  ExceptionListResponse,
  InlandMonitoringItem,
  MovementDetailResponse,
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
  TenantSummary,
  TenantUser,
} from "@steelops/contracts";

const baseUrl =
  process.env.INTERNAL_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

export async function getDashboardSnapshot(): Promise<DashboardSnapshot | null> {
  return getAuthenticatedJson<DashboardSnapshot>("/api/v1/dashboard/snapshot");
}

export async function getExecutiveDashboard(): Promise<ExecutiveDashboardResponse | null> {
  return getAuthenticatedJson<ExecutiveDashboardResponse>("/api/v1/dashboard/executive");
}

export async function getCurrentUser(): Promise<CurrentUser | null> {
  return getAuthenticatedJson<CurrentUser>("/api/v1/auth/me");
}

export async function getPilotReadiness(): Promise<PilotReadinessResponse | null> {
  return getAuthenticatedJson<PilotReadinessResponse>("/api/v1/dashboard/pilot-readiness");
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
  return (await getAuthenticatedJson<Shipment[]>(`/api/v1/shipments/visibility${suffix}`)) ?? [];
}

export async function getShipmentDetail(
  shipmentId: string,
): Promise<ShipmentDetailResponse | null> {
  return getAuthenticatedJson<ShipmentDetailResponse>(`/api/v1/shipments/${shipmentId}`);
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

export async function getSupplierDetail(supplierId: string): Promise<SupplierDetail | null> {
  return getAuthenticatedJson<SupplierDetail>(`/api/v1/suppliers/${supplierId}`);
}

export async function getSupplierPerformanceSummary(): Promise<SupplierPerformanceSummary | null> {
  return getAuthenticatedJson<SupplierPerformanceSummary>("/api/v1/suppliers/performance/summary");
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
  if (params?.owner_user_id) query.set("owner_user_id", String(params.owner_user_id));
  if (params?.unassigned_only) query.set("unassigned_only", "true");
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return getAuthenticatedJson<ExceptionListResponse>(`/api/v1/exceptions${suffix}`);
}

export async function getExceptionDetail(
  exceptionId: number,
): Promise<ExceptionDetailResponse | null> {
  return getAuthenticatedJson<ExceptionDetailResponse>(`/api/v1/exceptions/${exceptionId}`);
}

export async function getTenantUsers(): Promise<TenantUser[]> {
  return (await getAuthenticatedJson<TenantUser[]>("/api/v1/users")) ?? [];
}

export async function getUserProfile(userId: number): Promise<TenantUser | null> {
  return getAuthenticatedJson<TenantUser>(`/api/v1/users/${userId}`);
}

export async function getAllTenants(): Promise<TenantSummary[]> {
  return (await getAuthenticatedJson<TenantSummary[]>("/api/v1/tenants/admin/all")) ?? [];
}

export async function getSuperadminTenantUsers(tenantId: number): Promise<TenantUser[]> {
  return (
    (await getAuthenticatedJson<TenantUser[]>(`/api/v1/users/admin/tenant/${tenantId}`)) ?? []
  );
}

export async function getTenantDetails(tenantId: number): Promise<TenantDetail | null> {
  return getAuthenticatedJson<TenantDetail>(`/api/v1/tenants/admin/${tenantId}`);
}

export async function createTenant(payload: TenantCreatePayload): Promise<TenantCreateResponse | null> {
  const cookieStore = cookies();
  const token = cookieStore.get("steelops_token")?.value;
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

export async function activateTenant(tenantId: number): Promise<{ id: number; name: string; slug: string; is_active: boolean } | null> {
  const cookieStore = cookies();
  const token = cookieStore.get("steelops_token")?.value;
  if (!token) return null;

  try {
    const response = await fetch(`${baseUrl}/api/v1/tenants/admin/${tenantId}/activate`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) return null;
    return (await response.json()) as { id: number; name: string; slug: string; is_active: boolean };
  } catch {
    return null;
  }
}

export async function deactivateTenant(tenantId: number): Promise<{ id: number; name: string; slug: string; is_active: boolean } | null> {
  const cookieStore = cookies();
  const token = cookieStore.get("steelops_token")?.value;
  if (!token) return null;

  try {
    const response = await fetch(`${baseUrl}/api/v1/tenants/admin/${tenantId}/deactivate`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) return null;
    return (await response.json()) as { id: number; name: string; slug: string; is_active: boolean };
  } catch {
    return null;
  }
}

export async function deleteTenant(tenantId: number): Promise<boolean> {
  const cookieStore = cookies();
  const token = cookieStore.get("steelops_token")?.value;
  if (!token) return false;

  try {
    const response = await fetch(`${baseUrl}/api/v1/tenants/admin/${tenantId}`, {
      method: "DELETE",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    return response.ok;
  } catch {
    return false;
  }
}

async function getAuthenticatedJson<T>(path: string): Promise<T | null> {
  const cookieStore = cookies();
  const token = cookieStore.get("steelops_token")?.value;
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
