import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function GET(request: NextRequest) {
  const token = cookies().get("steelops_token")?.value;
  const tenantSlug = cookies().get("steelops_tenant")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const query = request.nextUrl.search;
  const response = await fetch(`${baseUrl}/api/v1/exceptions/export.csv${query}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
    },
  });

  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "text/csv",
      "Content-Disposition":
        response.headers.get("Content-Disposition") ?? 'attachment; filename="exceptions.csv"',
    },
  });
}
