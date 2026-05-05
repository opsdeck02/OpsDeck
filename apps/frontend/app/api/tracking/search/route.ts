import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const token = cookies().get("__Host-opsdeck-session")?.value;
  const tenantSlug = cookies().get("steelops_tenant")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const payload = await request.json();
  const response = await fetch(`${baseUrl}/api/v1/tracking/containers/search`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
    },
    body: JSON.stringify(payload),
  });

  return NextResponse.json(await response.json(), { status: response.status });
}
