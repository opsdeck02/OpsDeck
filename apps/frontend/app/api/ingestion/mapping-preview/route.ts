import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  const token = cookies().get("steelops_token")?.value;
  const tenantSlug = cookies().get("steelops_tenant")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const body = await request.formData();
  const response = await fetch(`${baseUrl}/api/v1/ingestion/mapping-preview`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
    },
    body,
  });

  return NextResponse.json(await response.json(), { status: response.status });
}
