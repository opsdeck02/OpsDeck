import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

function buildHeaders(token: string, tenantSlug: string | undefined, includeJson = false) {
  return {
    Authorization: `Bearer ${token}`,
    ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
    ...(includeJson ? { "Content-Type": "application/json" } : {}),
  };
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { sourceId: string } },
) {
  const token = cookies().get("steelops_token")?.value;
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }
  const tenantSlug = cookies().get("steelops_tenant")?.value;
  const body = await request.json();
  const response = await fetch(`${baseUrl}/api/v1/tenants/data-sources/${params.sourceId}`, {
    method: "PUT",
    headers: buildHeaders(token, tenantSlug, true),
    body: JSON.stringify(body),
  });
  return NextResponse.json(await response.json(), { status: response.status });
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: { sourceId: string } },
) {
  const token = cookies().get("steelops_token")?.value;
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }
  const tenantSlug = cookies().get("steelops_tenant")?.value;
  const response = await fetch(`${baseUrl}/api/v1/tenants/data-sources/${params.sourceId}`, {
    method: "DELETE",
    headers: buildHeaders(token, tenantSlug),
  });
  if (response.status === 204) {
    return new NextResponse(null, { status: 204 });
  }
  return NextResponse.json(await response.json(), { status: response.status });
}

export async function POST(
  _request: NextRequest,
  { params }: { params: { sourceId: string } },
) {
  const token = cookies().get("steelops_token")?.value;
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }
  const tenantSlug = cookies().get("steelops_tenant")?.value;
  const response = await fetch(`${baseUrl}/api/v1/tenants/data-sources/${params.sourceId}/sync`, {
    method: "POST",
    headers: buildHeaders(token, tenantSlug),
  });
  return NextResponse.json(await response.json(), { status: response.status });
}
