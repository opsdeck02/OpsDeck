import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function GET(
  _request: NextRequest,
  { params }: { params: { supplierId: string } },
) {
  return proxy(`/api/v1/suppliers/${params.supplierId}`);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { supplierId: string } },
) {
  const body = await request.json();
  return proxy(`/api/v1/suppliers/${params.supplierId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: { supplierId: string } },
) {
  return proxy(`/api/v1/suppliers/${params.supplierId}`, { method: "DELETE" });
}

async function proxy(path: string, init?: RequestInit) {
  const token = cookies().get("__Host-opsdeck-session")?.value;
  const tenantSlug = cookies().get("steelops_tenant")?.value;
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
      ...(init?.headers ?? {}),
    },
  });
  return NextResponse.json(await response.json(), { status: response.status });
}
