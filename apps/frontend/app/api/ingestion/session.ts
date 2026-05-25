import { cookies } from "next/headers";

export function getIngestionSession() {
  const cookieStore = cookies();
  return {
    token:
      cookieStore.get("__Host-opsdeck-session")?.value ??
      cookieStore.get("opsdeck-session")?.value,
    tenantSlug: cookieStore.get("steelops_tenant")?.value,
  };
}
