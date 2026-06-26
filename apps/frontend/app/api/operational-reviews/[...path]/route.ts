import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

async function proxy(
  request: NextRequest,
  { params }: { params: { path: string[] } },
  method: string,
) {
  const token =
    cookies().get("__Host-opsdeck-session")?.value ??
    cookies().get("opsdeck-session")?.value;

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const url = new URL(request.url);
  const body = ["POST", "PATCH", "PUT"].includes(method)
    ? await request.text()
    : undefined;
  const response = await fetch(
    `${baseUrl}/api/v1/operational-reviews/${params.path.join("/")}${url.search}`,
    {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body
          ? { "Content-Type": request.headers.get("content-type") ?? "application/json" }
          : {}),
      },
      body,
    },
  );

  if (response.status === 204) {
    return new NextResponse(null, { status: 204 });
  }
  return NextResponse.json(await response.json(), { status: response.status });
}

export async function GET(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context, "GET");
}

export async function POST(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context, "POST");
}

export async function PATCH(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context, "PATCH");
}

export async function DELETE(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context, "DELETE");
}
