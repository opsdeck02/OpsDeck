import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function PUT(
  request: NextRequest,
  { params }: { params: { dependencyId: string } },
) {
  const body = await request.json();
  return proxy(
    `/api/v1/impact/process-product-dependencies/${params.dependencyId}`,
    {
      method: "PUT",
      body: JSON.stringify(body),
    },
  );
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: { dependencyId: string } },
) {
  return proxy(
    `/api/v1/impact/process-product-dependencies/${params.dependencyId}`,
    { method: "DELETE" },
  );
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
  const text = await response.text();
  return new NextResponse(text, {
    status: response.status,
    headers: {
      "Content-Type":
        response.headers.get("Content-Type") ?? "application/json",
    },
  });
}
