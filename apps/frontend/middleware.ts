import { NextResponse, type NextRequest } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function middleware(request: NextRequest) {
  const token = request.cookies.get("__Host-opsdeck-session")?.value;
  const refreshToken = request.cookies.get("__Host-opsdeck-refresh")?.value;
  const isDashboardRoute = request.nextUrl.pathname.startsWith("/dashboard");

  if (isDashboardRoute && refreshToken && (!token || isJwtExpired(token))) {
    const refreshed = await refreshSession(refreshToken);
    if (refreshed?.access_token) {
      const response = NextResponse.next();
      response.cookies.set("__Host-opsdeck-session", refreshed.access_token, {
        httpOnly: true,
        sameSite: "strict",
        secure: true,
        path: "/",
        maxAge: 15 * 60,
      });
      return response;
    }
  }

  if (isDashboardRoute && !token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  if (request.nextUrl.pathname === "/login" && token) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

function isJwtExpired(token: string): boolean {
  try {
    const encodedPayload = (token.split(".")[1] ?? "").replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(encodedPayload)) as { exp?: number };
    return !payload.exp || payload.exp <= Math.floor(Date.now() / 1000) + 30;
  } catch {
    return true;
  }
}

async function refreshSession(refreshToken: string): Promise<{ access_token: string } | null> {
  try {
    const response = await fetch(`${baseUrl}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) return null;
    return (await response.json()) as { access_token: string };
  } catch {
    return null;
  }
}

export const config = {
  matcher: ["/dashboard/:path*", "/login"],
};
