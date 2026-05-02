import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function POST(
  _request: Request,
  { params }: { params: { tenantId: string } },
) {
  const token = cookies().get("__Host-opsdeck-session")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const response = await fetch(`${baseUrl}/api/v1/tenants/admin/${params.tenantId}/activate`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  return NextResponse.json(await response.json(), { status: response.status });
}
