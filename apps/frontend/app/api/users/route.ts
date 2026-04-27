import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const token = cookies().get("steelops_token")?.value;
  const tenantSlug = cookies().get("steelops_tenant")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const body = await request.json();
  const response = await fetch(`${baseUrl}/api/v1/users`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
    },
    body: JSON.stringify(body),
  });

  return NextResponse.json(await response.json(), { status: response.status });
}
