import { NextResponse, type NextRequest } from "next/server";

import { getIngestionSession } from "../../session";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function GET(
  _request: NextRequest,
  { params }: { params: { fileType: string } },
) {
  const { token, tenantSlug } = getIngestionSession();

  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const response = await fetch(`${baseUrl}/api/v1/ingestion/templates/${params.fileType}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      ...(tenantSlug ? { "X-Tenant-Slug": tenantSlug } : {}),
    },
  });
  const body = await response.text();

  return new NextResponse(body, {
    status: response.status,
    headers: {
      "Content-Type": "text/csv",
      "Content-Disposition": `attachment; filename="${params.fileType}_upload_template.csv"`,
    },
  });
}
