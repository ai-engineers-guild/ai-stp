import { randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { confirmCorporateInvitation } from "@/lib/api/corporate-invitations";
import { ApiError } from "@/lib/api/errors";
import {
  invitationClaimCookieName,
  invitationClaimCookiePath,
  invitationClaimFlagName,
} from "@/lib/auth/cookies";
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
 * Same-origin confirm hop for claimed organization invitations (#201).
 *
 * The confirmation token arrives only in the JSON body from a client that
 * read the emailed link's URL fragment. It proves the claimant controls the
 * invited inbox; the API binds the resulting membership to the session's
 * account.
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
  // Fresh registrations are onboarding_pending: the API rejects their confirm
  // until legal onboarding completes. Distinct code so the client redirects to
  // onboarding instead of looping back to login.
  if (session.accountStatus === "onboarding_pending") {
    return NextResponse.json(
      { error: { code: "AI_STP_ONBOARDING_REQUIRED", message: "complete onboarding first" } },
      { status: 409 },
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

  // Body token wins; otherwise the parked claim cookie — same revisit path
  // as accept: the emailed confirm link may land after a login round trip.
  const bodyToken = typeof body.token === "string" ? body.token : "";
  const token =
    bodyToken.length >= 8
      ? bodyToken
      : (jar.get(invitationClaimCookieName(invitationId, "confirm"))?.value ?? "");
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
    const result = await confirmCorporateInvitation(
      sessionToken,
      invitationId,
      token,
      idempotencyKey,
    );
    // Consumed: drop the parked claim and its flag (path must match `hold`).
    const claimPath = invitationClaimCookiePath(invitationId);
    jar.set(invitationClaimCookieName(invitationId, "confirm"), "", {
      path: claimPath,
      maxAge: 0,
    });
    jar.set(invitationClaimFlagName(invitationId, "confirm"), "", {
      path: "/",
      maxAge: 0,
    });
    const headers = new Headers();
    if (result.operationId) {
      headers.set("x-operation-id", result.operationId);
    }
    return NextResponse.json({ schema_version: 1, member: result.body }, { status: 200, headers });
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json(
        { error: { code: error.code, message: error.message } },
        { status: error.status || 400 },
      );
    }
    return NextResponse.json(
      { error: { code: "AI_STP_INTERNAL", message: "confirm failed" } },
      { status: 500 },
    );
  } finally {
    // Touch CSRF cookie name so static analysis sees the dual-submit pair.
    void CSRF_COOKIE;
  }
}
