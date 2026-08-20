"use server";

import { randomBytes } from "node:crypto";
import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";

import { confirmPublicationPlan } from "@/lib/api/publications";
import { startOwnerPublication } from "@/lib/api/owner";
import { ApiError } from "@/lib/api/errors";
import { assertCsrf, readCsrfToken, readSession, SESSION_COOKIE } from "@/lib/auth/session";

export async function startPublicationAction(input: {
  objectKind: "component" | "setup";
  stableId: string;
  version: string;
  deviceId: string;
  csrfToken: string;
}): Promise<{ planId: string; operationId: string | null }> {
  const cookieCsrf = await readCsrfToken();
  assertCsrf(input.csrfToken, cookieCsrf);
  const session = await readSession();
  if (!session) {
    throw new ApiError({ code: "AI_STP_UNAUTHORIZED", message: "not signed in", status: 401 });
  }
  const jar = await cookies();
  const sessionToken = jar.get(SESSION_COOKIE)?.value;
  if (!sessionToken) {
    throw new ApiError({ code: "AI_STP_UNAUTHORIZED", message: "not signed in", status: 401 });
  }
  const idempotencyKey = randomBytes(16).toString("hex");
  const result = await startOwnerPublication(
    sessionToken,
    input.objectKind,
    input.stableId,
    input.version,
    {
      device_id: input.deviceId,
      idempotency_key: idempotencyKey,
    },
  );
  revalidatePath("/[locale]/objects", "layout");
  return { planId: result.body.plan_id, operationId: result.operationId };
}

export async function confirmPublicationAction(input: {
  planId: string;
  planHash: string;
  csrfToken: string;
}): Promise<{ operationId: string | null; state: string }> {
  const cookieCsrf = await readCsrfToken();
  assertCsrf(input.csrfToken, cookieCsrf);
  const session = await readSession();
  if (!session) {
    throw new ApiError({ code: "AI_STP_UNAUTHORIZED", message: "not signed in", status: 401 });
  }
  const jar = await cookies();
  const sessionToken = jar.get(SESSION_COOKIE)?.value;
  if (!sessionToken) {
    throw new ApiError({ code: "AI_STP_UNAUTHORIZED", message: "not signed in", status: 401 });
  }
  const idempotencyKey = randomBytes(16).toString("hex");
  const result = await confirmPublicationPlan(
    sessionToken,
    input.planId,
    input.planHash,
    idempotencyKey,
  );
  revalidatePath(`/[locale]/publications/${input.planId}`, "page");
  return { operationId: result.operationId, state: result.body.state };
}
