import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { privateApiRequest } from "@/lib/api/http";
import { getEnv } from "@/lib/env";
import { startLocalSession, stopLocalSession } from "@/lib/local-api";
import {
  LOCAL_CSRF_COOKIE,
  LOCAL_API_BASE_COOKIE,
  LOCAL_SESSION_COOKIE,
  ORGANIZATION_COOKIE,
  PRODUCT_MODE_COOKIE,
} from "@/lib/context-cookies";

const ORGANIZATION_ID = /^organization_[0-7][0-9A-HJKMNP-TV-Z]{25}$/;

type ContextSelection = {
  mode: "local" | null;
  organizationId: string | null | undefined;
};

export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  if (origin && !isSameOrigin(request, origin)) {
    return NextResponse.json({ error: "cross-origin context selection denied" }, { status: 403 });
  }
  const body: unknown = await request.json().catch(() => undefined);
  const selection = parseSelection(body);
  if (selection instanceof NextResponse) return selection;

  const accessError = await checkOrganizationAccess(selection.organizationId);
  if (accessError) return accessError;
  let localSession:
    { session: string; csrf: string; expires_at: string; api_base_url?: string } | undefined;
  if (selection.mode === "local") {
    try {
      localSession = getEnv().AI_STP_USE_MOCKS
        ? await privateApiRequest<{
            session: string;
            csrf: string;
            expires_at: string;
            api_base_url?: string;
          }>("/v1/local/session", { method: "POST", baseUrl: getPrimaryApiBaseUrl() })
        : await startLocalSession((await cookies()).get(LOCAL_SESSION_COOKIE)?.value);
    } catch {
      return NextResponse.json({ error: "local session unavailable" }, { status: 503 });
    }
  } else if (hasCookie(request.headers.get("cookie"), LOCAL_SESSION_COOKIE)) {
    try {
      if (getEnv().AI_STP_USE_MOCKS)
        await privateApiRequest("/v1/local/session", {
          method: "DELETE",
          baseUrl: getPrimaryApiBaseUrl(),
        });
      else {
        const jar = await cookies();
        await stopLocalSession(
          jar.get(LOCAL_SESSION_COOKIE)?.value ?? "",
          jar.get(LOCAL_CSRF_COOKIE)?.value ?? "",
        );
      }
    } catch {
      return NextResponse.json({ error: "local session could not be ended" }, { status: 503 });
    }
  }
  return setContextCookies(selection, localSession);
}

function isSameOrigin(request: Request, origin: string): boolean {
  try {
    const actual = new URL(origin);
    const forwardedHost = request.headers.get("x-forwarded-host")?.split(",", 1)[0]?.trim();
    const host = forwardedHost ?? request.headers.get("host");
    const protocol =
      request.headers.get("x-forwarded-proto")?.split(",", 1)[0]?.trim() ??
      new URL(request.url).protocol.replace(/:$/, "");
    return host
      ? actual.protocol === `${protocol}:` && actual.host === host
      : origin === new URL(request.url).origin;
  } catch {
    return false;
  }
}

function hasCookie(header: string | null, name: string): boolean {
  return Boolean(
    header
      ?.split(";")
      .map((part) => part.trim().split("=", 1)[0])
      .includes(name),
  );
}

function parseSelection(body: unknown): ContextSelection | NextResponse {
  if (body === undefined || body === null || typeof body !== "object" || Array.isArray(body)) {
    return NextResponse.json({ error: "invalid context selection" }, { status: 400 });
  }
  const input = body as Record<string, unknown>;
  const value = input.organization_id;
  const mode = input.mode ?? null;
  if (Object.keys(input).some((key) => key !== "organization_id" && key !== "mode")) {
    return NextResponse.json({ error: "invalid context selection" }, { status: 400 });
  }
  if (mode !== null && mode !== "local") {
    return NextResponse.json({ error: "invalid context mode" }, { status: 400 });
  }
  if (mode === "local" && value !== undefined && value !== null) {
    return NextResponse.json(
      { error: "local context cannot name an organization" },
      { status: 400 },
    );
  }
  if (
    value !== undefined &&
    value !== null &&
    (typeof value !== "string" || !ORGANIZATION_ID.test(value))
  ) {
    return NextResponse.json({ error: "invalid organization" }, { status: 400 });
  }
  return { mode, organizationId: value };
}

async function checkOrganizationAccess(
  organizationId: string | null | undefined,
): Promise<NextResponse | null> {
  if (typeof organizationId !== "string") return null;
  try {
    const context = await privateApiRequest<{ organization_id: string | null; mode: string }>(
      "/v1/context",
      { headers: { "X-AI-STP-Organization-Id": organizationId }, baseUrl: getPrimaryApiBaseUrl() },
    );
    return context.mode === "local" || context.organization_id !== organizationId
      ? NextResponse.json({ error: "organization access denied" }, { status: 403 })
      : null;
  } catch (error) {
    const statusValue =
      error !== null && typeof error === "object" && "status" in error
        ? (error as { status?: unknown }).status
        : undefined;
    const status = typeof statusValue === "number" && statusValue > 0 ? statusValue : 503;
    return NextResponse.json({ error: "organization access denied" }, { status });
  }
}

function setContextCookies(
  selection: ContextSelection,
  localSession?: { session: string; csrf: string; expires_at: string; api_base_url?: string },
): NextResponse {
  const response = NextResponse.json({ ok: true });
  response.headers.set("Cache-Control", "private, no-store");
  if (selection.mode === "local") {
    response.cookies.delete(ORGANIZATION_COOKIE);
    response.cookies.delete(LOCAL_API_BASE_COOKIE);
    response.cookies.set(PRODUCT_MODE_COOKIE, "local", {
      httpOnly: true,
      maxAge: 60 * 60 * 24 * 30,
      path: "/",
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
    });
    if (localSession) {
      const expires = new Date(localSession.expires_at);
      response.cookies.set(LOCAL_SESSION_COOKIE, localSession.session, {
        httpOnly: true,
        expires,
        path: "/",
        sameSite: "lax",
        secure: process.env.NODE_ENV === "production",
      });
      response.cookies.set(LOCAL_CSRF_COOKIE, localSession.csrf, {
        httpOnly: true,
        expires,
        path: "/",
        sameSite: "lax",
        secure: process.env.NODE_ENV === "production",
      });
      if (localSession.api_base_url) {
        response.cookies.set(LOCAL_API_BASE_COOKIE, localSession.api_base_url, {
          httpOnly: true,
          expires,
          path: "/",
          sameSite: "lax",
          secure: process.env.NODE_ENV === "production",
        });
      }
    }
  } else if (selection.organizationId === undefined || selection.organizationId === null) {
    response.cookies.delete(ORGANIZATION_COOKIE);
    response.cookies.delete(PRODUCT_MODE_COOKIE);
    response.cookies.delete(LOCAL_SESSION_COOKIE);
    response.cookies.delete(LOCAL_CSRF_COOKIE);
    response.cookies.delete(LOCAL_API_BASE_COOKIE);
  } else {
    response.cookies.delete(PRODUCT_MODE_COOKIE);
    response.cookies.set(ORGANIZATION_COOKIE, selection.organizationId, {
      httpOnly: true,
      maxAge: 60 * 60 * 24 * 30,
      path: "/",
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
    });
    response.cookies.delete(LOCAL_SESSION_COOKIE);
    response.cookies.delete(LOCAL_CSRF_COOKIE);
    response.cookies.delete(LOCAL_API_BASE_COOKIE);
  }
  return response;
}

function getPrimaryApiBaseUrl(): string {
  return (process.env.AI_STP_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}
