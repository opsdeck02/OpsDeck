import { NextResponse } from "next/server";

export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete("__Host-opsdeck-session");
  response.cookies.delete("__Host-opsdeck-refresh");
  response.cookies.delete("steelops_tenant");
  return response;
}
