import { NextResponse } from "next/server";

import { getIngestionSession, ingestionJsonResponse } from "../session";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  const { token, tenantSlug } = getIngestionSession();

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const body = await request.formData();
  const response = await fetch(`${baseUrl}/api/v1/ingestion/url-mapping-preview`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
    },
    body,
  });

  return ingestionJsonResponse(response);
}
