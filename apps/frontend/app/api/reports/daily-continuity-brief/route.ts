import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function GET() {
  const token = cookies().get("__Host-opsdeck-session")?.value;
  const tenantSlug = cookies().get("steelops_tenant")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const response = await fetch(`${baseUrl}/api/v1/reports/daily-continuity-brief`, {
    headers: {
      Authorization: `Bearer ${token}`,
      ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
    },
  });

  const body = await response.arrayBuffer();
  return new NextResponse(body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/pdf",
      "Content-Disposition":
        response.headers.get("Content-Disposition") ??
        'attachment; filename="opsdeck-daily-continuity-brief.pdf"',
      "Cache-Control": "no-store",
    },
  });
}

