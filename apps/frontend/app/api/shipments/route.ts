import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function GET() {
  const token = cookies().get("__Host-opsdeck-session")?.value;
  const tenantSlug = cookies().get("steelops_tenant")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const response = await fetch(`${baseUrl}/api/v1/tracking/shipments`, {
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
    },
  });

  return NextResponse.json(await readJson(response), { status: response.status });
}

async function readJson(response: Response) {
  try {
    return await response.json();
  } catch {
    return { detail: "Shipment API returned an invalid response." };
  }
}
