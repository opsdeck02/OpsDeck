import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function GET(request: NextRequest) {
  const token = cookies().get("__Host-opsdeck-session")?.value;
  const tenantSlug = cookies().get("steelops_tenant")?.value;
  const vesselName = request.nextUrl.searchParams.get("vessel_name");

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }
  if (!vesselName) {
    return NextResponse.json({ detail: "Vessel name is required" }, { status: 400 });
  }

  const params = new URLSearchParams({ vessel_name: vesselName });
  const response = await fetch(`${baseUrl}/api/v1/tracking/vessels/position?${params}`, {
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
    return { detail: "Vessel tracking API returned an invalid response." };
  }
}
