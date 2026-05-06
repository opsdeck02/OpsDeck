import { NextResponse, type NextRequest } from "next/server";

const baseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";

export async function GET(request: NextRequest) {
  const origin = publicOrigin(request);
  const callbackUrl = new URL(`${baseUrl}/api/v1/microsoft/callback`);
  request.nextUrl.searchParams.forEach((value, key) => {
    callbackUrl.searchParams.set(key, value);
  });

  try {
    const response = await fetch(callbackUrl, { redirect: "manual" });
    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get("location") ?? "/dashboard/onboarding?microsoft=connected";
      return NextResponse.redirect(new URL(location, origin));
    }

    const message = response.ok ? "connected" : "error";
    return NextResponse.redirect(
      new URL(`/dashboard/onboarding?microsoft=${message}`, origin),
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Microsoft callback failed";
    const redirectUrl = new URL("/dashboard/onboarding", origin);
    redirectUrl.searchParams.set("microsoft", "error");
    redirectUrl.searchParams.set("message", message);
    return NextResponse.redirect(redirectUrl);
  }
}

function publicOrigin(request: NextRequest): string {
  const forwardedHost = request.headers.get("x-forwarded-host");
  const forwardedProto = request.headers.get("x-forwarded-proto") ?? "https";
  if (forwardedHost) {
    return `${forwardedProto}://${forwardedHost}`;
  }
  return request.nextUrl.origin;
}
