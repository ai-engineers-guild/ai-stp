"use server";

import { randomBytes } from "node:crypto";
import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";

import { createReportCase } from "@/lib/api/reports";
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

export async function createReportAction(input: {
  csrfToken: string;
  objectKind: "component" | "setup";
  stableId: string;
  version: string;
  contentDigest: string;
  diagnostics: string;
  diagnosticsPreviewed: boolean;
  vulnerability: boolean;
  errorCode?: string;
}): Promise<{ caseId: string; operationId: string | null }> {
  assertCsrf(input.csrfToken, await readCsrfToken());
  if (!input.diagnosticsPreviewed) {
    throw new ApiError({
      code: "AI_STP_VALIDATION_ERROR",
      message: "diagnostics preview required",
      status: 400,
    });
  }
  // Size guard and path cleanup before the contract max_length.
  const diagnostics = input.diagnostics
    .replaceAll(/[A-Za-z]:\\[^\s]+/g, "[path]")
    .replaceAll(/\/(?:home|Users|var|tmp)\/[^\s]+/g, "[path]")
    .slice(0, 4000);
  const sessionToken = await sessionTokenOrThrow();
  const result = await createReportCase(sessionToken, {
    object_kind: input.objectKind,
    stable_id: input.stableId,
    version: input.version,
    content_digest: input.contentDigest,
    diagnostics,
    diagnostics_previewed: true,
    vulnerability: input.vulnerability,
    ...(input.errorCode ? { error_code: input.errorCode } : {}),
    idempotency_key: randomBytes(16).toString("hex"),
  });
  revalidatePath("/[locale]/reports", "page");
  return { caseId: result.body.case_id, operationId: result.operationId };
}
