import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function POST(
  _request: NextRequest,
  { params }: { params: { supplierId: string } },
) {
  const token = cookies().get("__Host-opsdeck-session")?.value;
  const tenantSlug = cookies().get("steelops_tenant")?.value;
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }
  const response = await fetch(
    `${baseUrl}/api/v1/suppliers/${params.supplierId}/link-shipments`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
      },
    },
  );
  return NextResponse.json(await response.json(), { status: response.status });
}
