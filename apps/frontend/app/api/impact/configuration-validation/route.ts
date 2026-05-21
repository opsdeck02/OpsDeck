import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function GET(request: NextRequest) {
  const token =
    cookies().get("__Host-opsdeck-session")?.value ??
    cookies().get("opsdeck-session")?.value;
  const tenantSlug = cookies().get("steelops_tenant")?.value;
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }
  const response = await fetch(
    `${baseUrl}/api/v1/impact/configuration-validation${request.nextUrl.search}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
      },
    },
  );
  const text = await response.text();
  return new NextResponse(text, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/json",
    },
  });
}
