import { NextResponse } from "next/server";

const expiredCookieOptions = {
  httpOnly: true,
  sameSite: "lax" as const,
  secure: true,
  path: "/",
  maxAge: 0,
  expires: new Date(0),
};

export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set("__Host-opsdeck-session", "", expiredCookieOptions);
  response.cookies.set("__Host-opsdeck-refresh", "", expiredCookieOptions);
  response.cookies.set("steelops_tenant", "", expiredCookieOptions);
  return response;
}
