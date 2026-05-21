import { NextResponse } from "next/server";

const productionExpiredCookieOptions = {
  httpOnly: true,
  sameSite: "lax" as const,
  secure: true,
  path: "/",
  maxAge: 0,
  expires: new Date(0),
};

const developmentExpiredCookieOptions = {
  ...productionExpiredCookieOptions,
  secure: false,
};

export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set("__Host-opsdeck-session", "", productionExpiredCookieOptions);
  response.cookies.set("__Host-opsdeck-refresh", "", productionExpiredCookieOptions);
  response.cookies.set("opsdeck-session", "", developmentExpiredCookieOptions);
  response.cookies.set("opsdeck-refresh", "", developmentExpiredCookieOptions);
  response.cookies.set("steelops_tenant", "", developmentExpiredCookieOptions);
  return response;
}
