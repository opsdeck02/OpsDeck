import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function GET() {
  const token = cookies().get("__Host-opsdeck-session")?.value;
  const tenantSlug = cookies().get("steelops_tenant")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const response = await fetch(`${baseUrl}/api/v1/dashboard/executive/export.csv`, {
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
        response.headers.get("Content-Disposition") ?? 'attachment; filename="executive_dashboard.csv"',
    },
  });
}
