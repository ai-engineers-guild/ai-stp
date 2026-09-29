import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  invitationClaimCookieName,
  invitationClaimCookiePath,
  invitationClaimFlagName,
  type InvitationClaimVariant,
} from "@/lib/auth/cookies";
import { assertCsrf, readCsrfToken } from "@/lib/auth/session";
import { getEnv } from "@/lib/env";

type RouteContext = {
  params: Promise<{ invitationId: string }>;
};

const INVITATION_ID_PATTERN = /^[A-Za-z0-9_-]{8,64}$/;

/**
 * Same-origin claim parking for organization invitations (#201).
 *
 * The client read the emailed token from the URL fragment and POSTs it here
 * once; the token moves into an httpOnly cookie scoped to this invitation's
 * API path. It survives reloads and the login/onboarding round trip and is
 * never readable from JS — no storage, no logs, no server props. A paired
 * JS-readable flag cookie only marks "a claim is held" so the accept page can
 * render its button on a fragment-less revisit; it carries no secret.
 */
export async function POST(request: Request, context: RouteContext) {
  const { invitationId } = await context.params;
  if (!INVITATION_ID_PATTERN.test(invitationId)) {
    return NextResponse.json(
      { error: { code: "AI_STP_VALIDATION_ERROR", message: "invalid invitation" } },
      { status: 400 },
    );
  }
  try {
    assertCsrf(request.headers.get("x-csrf-token"), await readCsrfToken());
  } catch {
    // Anonymous visitors hold no CSRF cookie — the fragment in `returnTo`
    // covers that leg; the cookie is parked after login instead.
    return NextResponse.json(
      { error: { code: "AI_STP_FORBIDDEN", message: "csrf failed" } },
      { status: 403 },
    );
  }

  let body: { token?: unknown; variant?: unknown };
  try {
    body = (await request.json()) as { token?: unknown; variant?: unknown };
  } catch {
    return NextResponse.json(
      { error: { code: "AI_STP_VALIDATION_ERROR", message: "invalid body" } },
      { status: 400 },
    );
  }
  const token = typeof body.token === "string" ? body.token : "";
  if (token.length < 8 || token.length > 512) {
    return NextResponse.json(
      { error: { code: "AI_STP_VALIDATION_ERROR", message: "token required" } },
      { status: 400 },
    );
  }
  const variant: InvitationClaimVariant = body.variant === "confirm" ? "confirm" : "accept";

  const path = invitationClaimCookiePath(invitationId);
  const maxAge = getEnv().AI_STP_INVITATION_CLAIM_TTL_SECONDS;
  const secure = process.env.NODE_ENV === "production";
  const jar = await cookies();
  jar.set(invitationClaimCookieName(invitationId, variant), token, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path,
    maxAge,
  });
  jar.set(invitationClaimFlagName(invitationId, variant), "1", {
    httpOnly: false,
    secure,
    sameSite: "lax",
    // Broad on purpose: the flag carries no secret, and the accept page must
    // see it via document.cookie — a /api-scoped path would be invisible.
    path: "/",
    maxAge,
  });
  return new NextResponse(null, { status: 204 });
}
