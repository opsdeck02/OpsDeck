import type { RoleName } from "@steelops/contracts";

export function isOperatorRole(role: RoleName | null | undefined): boolean {
  return (
    role === "tenant_admin" ||
    role === "buyer_user" ||
    role === "logistics_user" ||
    role === "planner_user"
  );
}

export function isSponsorViewerRole(role: RoleName | null | undefined): boolean {
  return role === "management_user" || role === "sponsor_user";
}

export function canManageOperationalWorkflow(role: RoleName | null | undefined): boolean {
  return isOperatorRole(role);
}

export function canAccessPilotAdmin(role: RoleName | null | undefined): boolean {
  return role === "tenant_admin";
}

export function canAccessSuperadmin(user: { is_superadmin?: boolean } | null | undefined): boolean {
  return Boolean(user?.is_superadmin);
}

export function formatRoleLabel(role: RoleName | null | undefined): string {
  if (role === "tenant_admin") {
    return "tenant admin";
  }
  if (role === "buyer_user") {
    return "buyer";
  }
  if (role === "logistics_user") {
    return "logistics";
  }
  if (role === "management_user") {
    return "management";
  }
  if (role === "sponsor_user") {
    return "sponsor viewer";
  }
  if (role === "planner_user") {
    return "planner";
  }
  return "unknown";
}
