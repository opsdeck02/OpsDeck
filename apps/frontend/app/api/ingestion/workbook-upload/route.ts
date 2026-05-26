import { NextResponse, type NextRequest } from "next/server";

import { getIngestionSession, ingestionJsonResponse } from "../session";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const { token, tenantSlug } = getIngestionSession();

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const formData = await request.formData();
  const response = await fetch(`${baseUrl}/api/v1/ingestion/workbook-upload`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
    },
    body: formData,
  });

  return ingestionJsonResponse(response);
}
