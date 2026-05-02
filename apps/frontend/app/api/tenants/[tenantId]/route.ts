import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function PATCH(
  request: NextRequest,
  { params }: { params: { tenantId: string } },
) {
  const token = cookies().get("__Host-opsdeck-session")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const body = await request.json();
  const response = await fetch(`${baseUrl}/api/v1/tenants/admin/${params.tenantId}/plan`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  return NextResponse.json(await response.json(), { status: response.status });
}

export async function DELETE(
  _request: Request,
  { params }: { params: { tenantId: string } },
) {
  const token = cookies().get("__Host-opsdeck-session")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const response = await fetch(`${baseUrl}/api/v1/tenants/admin/${params.tenantId}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (response.status === 204) {
    return new NextResponse(null, { status: 204 });
  }

  return NextResponse.json(await response.json(), { status: response.status });
}
