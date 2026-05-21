import { NextResponse, type NextRequest } from "next/server";

import type { LoginResponse } from "@steelops/contracts";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";
const isProduction = process.env.NODE_ENV === "production";
const sessionCookieName = isProduction ? "__Host-opsdeck-session" : "opsdeck-session";
const refreshCookieName = isProduction ? "__Host-opsdeck-refresh" : "opsdeck-refresh";

export async function POST(request: NextRequest) {
  const payload = await request.json();

  try {
    const apiResponse = await fetch(`${baseUrl}/api/v1/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!apiResponse.ok) {
      const errorBody = (await apiResponse.json().catch(() => null)) as { detail?: string } | null;
      return NextResponse.json(
        { detail: errorBody?.detail ?? "Invalid email or password" },
        { status: apiResponse.status },
      );
    }

    const body = (await apiResponse.json()) as LoginResponse;
    const activeMembership = body.user.memberships[0];
    const response = NextResponse.json({
      ...body,
      // Keep the response shape stable, but never expose raw JWTs to browser JS.
      access_token: "",
      refresh_token: null,
    });

    response.cookies.set(sessionCookieName, body.access_token, {
      httpOnly: true,
      sameSite: "lax",
      secure: isProduction,
      path: "/",
      maxAge: 15 * 60,
    });
    if (body.refresh_token) {
      response.cookies.set(refreshCookieName, body.refresh_token, {
        httpOnly: true,
        sameSite: "lax",
        secure: isProduction,
        path: "/",
        maxAge: 7 * 24 * 60 * 60,
      });
    }
    response.cookies.set("steelops_tenant", activeMembership?.tenant_slug ?? "", {
      httpOnly: true,
      sameSite: "lax",
      secure: isProduction,
      path: "/",
      maxAge: activeMembership ? 7 * 24 * 60 * 60 : 0,
    });

    return response;
  } catch {
    return NextResponse.json(
      { detail: `Auth service unavailable at ${baseUrl}` },
      { status: 502 },
    );
  }
}
