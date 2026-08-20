"use server";

import { randomBytes } from "node:crypto";
import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";

import {
  createDirectGrant,
  createGrantInvitation,
  revokeAccessGrant,
  revokeGrantInvitation,
} from "@/lib/api/grants";
import { ApiError } from "@/lib/api/errors";
import { assertCsrf, readCsrfToken, readSession, SESSION_COOKIE } from "@/lib/auth/session";

async function sessionTokenOrThrow(): Promise<string> {
  const session = await readSession();
  if (!session) {
    throw new ApiError({ code: "AI_STP_UNAUTHORIZED", message: "not signed in", status: 401 });
  }
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) {
    throw new ApiError({ code: "AI_STP_UNAUTHORIZED", message: "not signed in", status: 401 });
  }
  return token;
}

export async function createInvitationAction(input: {
  csrfToken: string;
  objectKind: "component" | "setup";
  stableId: string;
  major: number;
  recipientEmail: string;
}): Promise<{ operationId: string | null }> {
  assertCsrf(input.csrfToken, await readCsrfToken());
  const sessionToken = await sessionTokenOrThrow();
  const result = await createGrantInvitation(sessionToken, {
    object_kind: input.objectKind,
    stable_id: input.stableId,
    major: input.major,
    recipient_email: input.recipientEmail,
    idempotency_key: randomBytes(16).toString("hex"),
  });
  revalidatePath("/[locale]/access", "page");
  return { operationId: result.operationId };
}

export async function createDirectGrantAction(input: {
  csrfToken: string;
  objectKind: "component" | "setup";
  stableId: string;
  major: number;
  recipientKind: "github_username" | "user_id";
  recipient: string;
}): Promise<{ operationId: string | null }> {
  assertCsrf(input.csrfToken, await readCsrfToken());
  const sessionToken = await sessionTokenOrThrow();
  const result = await createDirectGrant(sessionToken, {
    object_kind: input.objectKind,
    stable_id: input.stableId,
    major: input.major,
    recipient_kind: input.recipientKind,
    recipient: input.recipient,
    idempotency_key: randomBytes(16).toString("hex"),
  });
  revalidatePath("/[locale]/access", "page");
  return { operationId: result.operationId };
}

export async function revokeInvitationAction(input: {
  csrfToken: string;
  invitationId: string;
  reason: string;
}): Promise<{ operationId: string | null }> {
  assertCsrf(input.csrfToken, await readCsrfToken());
  const sessionToken = await sessionTokenOrThrow();
  const result = await revokeGrantInvitation(
    sessionToken,
    input.invitationId,
    input.reason,
    randomBytes(16).toString("hex"),
  );
  revalidatePath("/[locale]/access", "page");
  return { operationId: result.operationId };
}

export async function revokeGrantAction(input: {
  csrfToken: string;
  grantId: string;
  reason: string;
}): Promise<{ operationId: string | null }> {
  assertCsrf(input.csrfToken, await readCsrfToken());
  const sessionToken = await sessionTokenOrThrow();
  const result = await revokeAccessGrant(
    sessionToken,
    input.grantId,
    input.reason,
    randomBytes(16).toString("hex"),
  );
  revalidatePath("/[locale]/access", "page");
  return { operationId: result.operationId };
}
