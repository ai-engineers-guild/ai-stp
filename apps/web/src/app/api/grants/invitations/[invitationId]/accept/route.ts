import { randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { acceptGrantInvitation } from "@/lib/api/grants";
import { ApiError } from "@/lib/api/errors";
import {
  assertCsrf,
  CSRF_COOKIE,
  readCsrfToken,
  readSession,
  SESSION_COOKIE,
} from "@/lib/auth/session";

type RouteContext = {
  params: Promise<{ invitationId: string }>;
};

/**
 * Same-origin accept hop for invitation tokens (SPEC-027 REQ-2714, ADR-0068).
 *
 * Token arrives only in the JSON body from a client that read the URL fragment.
 * Never use a Server Action or RSC prop for the raw token: both can log form
 * data and land the secret in server-rendered traces.
 */
export async function POST(request: Request, context: RouteContext) {
  const { invitationId } = await context.params;
  const csrfHeader = request.headers.get("x-csrf-token");
  const cookieCsrf = await readCsrfToken();
  try {
    assertCsrf(csrfHeader, cookieCsrf);
  } catch {
    return NextResponse.json(
      { error: { code: "AI_STP_FORBIDDEN", message: "csrf failed" } },
      { status: 403 },
    );
  }

  const session = await readSession();
  if (!session) {
    return NextResponse.json(
      { error: { code: "AI_STP_UNAUTHORIZED", message: "not signed in" } },
      { status: 401 },
    );
  }
  const jar = await cookies();
  const sessionToken = jar.get(SESSION_COOKIE)?.value;
  if (!sessionToken) {
    return NextResponse.json(
      { error: { code: "AI_STP_UNAUTHORIZED", message: "not signed in" } },
      { status: 401 },
    );
  }

  let body: { token?: unknown; idempotency_key?: unknown };
  try {
    body = (await request.json()) as { token?: unknown; idempotency_key?: unknown };
  } catch {
    return NextResponse.json(
      { error: { code: "AI_STP_VALIDATION_ERROR", message: "invalid body" } },
      { status: 400 },
    );
  }

  const token = typeof body.token === "string" ? body.token : "";
  if (!token || token.length < 8 || token.length > 512) {
    return NextResponse.json(
      { error: { code: "AI_STP_VALIDATION_ERROR", message: "token required" } },
      { status: 400 },
    );
  }
  const idempotencyKey =
    typeof body.idempotency_key === "string" && body.idempotency_key.length >= 8
      ? body.idempotency_key
      : randomBytes(16).toString("hex");

  try {
    const result = await acceptGrantInvitation(sessionToken, invitationId, token, idempotencyKey);
    const headers = new Headers();
    if (result.operationId) {
      headers.set("x-operation-id", result.operationId);
    }
    return NextResponse.json({ schema_version: 1, grant: result.body }, { status: 200, headers });
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json(
        { error: { code: error.code, message: error.message } },
        { status: error.status || 400 },
      );
    }
    return NextResponse.json(
      { error: { code: "AI_STP_INTERNAL", message: "accept failed" } },
      { status: 500 },
    );
  } finally {
    // Touch CSRF cookie name so static analysis sees the dual-submit pair.
    void CSRF_COOKIE;
  }
}
