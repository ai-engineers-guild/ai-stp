"use server";

import { randomBytes } from "node:crypto";
import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";

import { getTranslations } from "next-intl/server";

import { staffTriageReport, staffVersionLifecycle } from "@/lib/api/reports";
import { ApiError } from "@/lib/api/errors";
import { readSession, requireCsrf, SESSION_COOKIE } from "@/lib/auth/session";

async function sessionTokenOrThrow(): Promise<string> {
  const common = await getTranslations("common");
  const session = await readSession();
  if (!session) {
    throw new ApiError({
      code: "AI_STP_UNAUTHORIZED",
      message: common("notSignedIn"),
      status: 401,
    });
  }
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) {
    throw new ApiError({
      code: "AI_STP_UNAUTHORIZED",
      message: common("notSignedIn"),
      status: 401,
    });
  }
  return token;
}

export async function staffTriageAction(input: {
  csrfToken: string;
  caseId: string;
  state: "triaged" | "awaiting_author" | "security_escalated" | "resolved" | "dismissed";
  reason: string;
  publicResponse?: string;
}): Promise<{ operationId: string | null }> {
  await requireCsrf(input.csrfToken);
  if (!input.reason.trim()) {
    const staff = await getTranslations("staff");
    throw new ApiError({
      code: "AI_STP_VALIDATION_ERROR",
      message: staff("reasonRequired"),
      status: 400,
    });
  }
  const sessionToken = await sessionTokenOrThrow();
  const result = await staffTriageReport(
    sessionToken,
    input.caseId,
    input.state,
    input.reason.trim(),
    randomBytes(16).toString("hex"),
    input.publicResponse?.trim() ?? "",
  );
  revalidatePath("/[locale]/staff/reports", "layout");
  return { operationId: result.operationId };
}

export async function staffLifecycleAction(input: {
  csrfToken: string;
  objectKind: "component" | "setup";
  stableId: string;
  version: string;
  action: "block" | "hide" | "restore";
  reason: string;
}): Promise<{ operationId: string | null }> {
  await requireCsrf(input.csrfToken);
  if (!input.reason.trim()) {
    const staff = await getTranslations("staff");
    throw new ApiError({
      code: "AI_STP_VALIDATION_ERROR",
      message: staff("reasonRequired"),
      status: 400,
    });
  }
  const sessionToken = await sessionTokenOrThrow();
  const result = await staffVersionLifecycle(sessionToken, {
    object_kind: input.objectKind,
    stable_id: input.stableId,
    version: input.version,
    action: input.action,
    reason: input.reason.trim(),
    idempotency_key: randomBytes(16).toString("hex"),
  });
  revalidatePath("/[locale]/staff/reports", "layout");
  return { operationId: result.operationId };
}
