import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export function getIngestionSession() {
  const cookieStore = cookies();
  return {
    token:
      cookieStore.get("__Host-opsdeck-session")?.value ??
      cookieStore.get("opsdeck-session")?.value,
    tenantSlug: cookieStore.get("steelops_tenant")?.value,
  };
}

export async function ingestionJsonResponse(response: Response) {
  const text = await response.text();
  let payload: unknown;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = {
      detail:
        text.trim() ||
        `Ingestion service returned a non-JSON response with status ${response.status}.`,
    };
  }
  return NextResponse.json(payload, { status: response.status });
}
