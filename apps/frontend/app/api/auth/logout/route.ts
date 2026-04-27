import { NextResponse } from "next/server";

export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete("steelops_token");
  response.cookies.delete("steelops_tenant");
  return response;
}
