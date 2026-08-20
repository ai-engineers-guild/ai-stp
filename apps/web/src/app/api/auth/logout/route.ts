import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { CSRF_COOKIE, SESSION_COOKIE } from "@/lib/auth/cookies";
import { getEnv } from "@/lib/env";

/**
 * Session-clearing route handler (ADR-0041). Route handlers may modify cookies,
 * so explicit logout (POST) and stale-session redirect (GET, from requireSession)
 * clear the session and CSRF cookies here.
 *
 * The Location is RELATIVE on purpose: inside the container request.url is
 * often http://0.0.0.0:3000/..., so an absolute redirect built from it leaks
 * an unreachable host to the browser (ERR_ADDRESS_INVALID). A relative
 * Location is resolved by the browser against the public origin.
 */
function clearAndRedirect(location: string): NextResponse {
  const res = new NextResponse(null, { status: 303, headers: { Location: location } });
  res.cookies.delete(SESSION_COOKIE);
  res.cookies.delete(CSRF_COOKIE);
  return res;
}

function localeOf(request: Request): string {
  const value = new URL(request.url).searchParams.get("locale");
  return value === "en" || value === "ru" ? value : "ru";
}

/**
 * Best-effort server-side revoke against the real API. Failures still clear
 * local cookies so the browser cannot keep a stale opaque session.
 */
async function revokeServerSession(): Promise<void> {
  const env = getEnv();
  if (env.AI_STP_USE_MOCKS) {
    return;
  }
  const jar = await cookies();
  const session = jar.get(SESSION_COOKIE)?.value;
  if (!session) {
    return;
  }
  const csrf = jar.get(CSRF_COOKIE)?.value;
  const cookieParts = [`${SESSION_COOKIE}=${session}`];
  if (csrf) {
    cookieParts.push(`${CSRF_COOKIE}=${csrf}`);
  }
  const headers: Record<string, string> = {
    Accept: "application/json",
    Cookie: cookieParts.join("; "),
  };
  if (csrf) {
    headers["X-CSRF-Token"] = csrf;
  }
  const base = env.AI_STP_API_BASE_URL.replace(/\/$/, "");
  try {
    await fetch(`${base}/v1/auth/logout`, {
      method: "POST",
      headers,
      cache: "no-store",
    });
  } catch {
    // Local cookie clear still proceeds below.
  }
}

export async function POST(request: Request): Promise<NextResponse> {
  await revokeServerSession();
  return clearAndRedirect(`/${localeOf(request)}/login`);
}

export function GET(request: Request): NextResponse {
  const url = new URL(request.url);
  const locale = localeOf(request);
  const params = new URLSearchParams();
  const returnTo = url.searchParams.get("returnTo");
  const reason = url.searchParams.get("reason");
  if (returnTo) {
    params.set("returnTo", returnTo);
  }
  if (reason) {
    params.set("reason", reason);
  }
  // Stale-session GET only clears local cookies; do not revoke a still-valid
  // server session when middleware bounced a parse failure.
  const qs = params.toString();
  return clearAndRedirect(`/${locale}/login${qs ? `?${qs}` : ""}`);
}
