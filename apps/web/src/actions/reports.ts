"use server";

import { randomBytes } from "node:crypto";
import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";

import { createReportCase } from "@/lib/api/reports";
import { ApiError } from "@/lib/api/errors";
import { assertCsrf, readCsrfToken, readSession, SESSION_COOKIE } from "@/lib/auth/session";
import type { ReportTopic } from "@/components/organisms/report-form";

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
  topic: ReportTopic;
  locale: "ru" | "en";
  objectKind: "component" | "setup";
  stableId: string;
  version: string;
  contentDigest: string;
  diagnostics: string;
  diagnosticsPreviewed: boolean;
  vulnerability: boolean;
  errorCode?: string;
  subject?: string;
  message?: string;
  evidence?: string;
  authorAccountId?: string;
  recipientAccountId?: string;
  service?: {
    name: string;
    primary_url: string;
    description_ru: string;
    description_en: string;
    source_url: string;
    country_codes: string[];
  };
  country?: { code: string; name_ru: string; name_en: string };
}): Promise<{ caseId: string; operationId: string | null }> {
  assertCsrf(input.csrfToken, await readCsrfToken());
  if (!input.diagnosticsPreviewed) {
    throw new ApiError({
      code: "AI_STP_VALIDATION_ERROR",
      message: "diagnostics preview required",
      status: 400,
    });
  }
  const diagnostics = input.diagnostics
    .replaceAll(/[A-Za-z]:\\[^\s]+/g, "[path]")
    .replaceAll(/\/(?:home|Users|var|tmp)\/[^\s]+/g, "[path]")
    .slice(0, 4000);
  const sessionToken = await sessionTokenOrThrow();
  const result = await createReportCase(sessionToken, {
    topic: input.topic,
    locale: input.locale,
    ...(input.topic === "object_report"
      ? {
          object_kind: input.objectKind,
          stable_id: input.stableId,
          version: input.version,
          content_digest: input.contentDigest,
        }
      : input.topic === "component_complaint" || input.topic === "ownership_transfer"
        ? { object_kind: "component" as const, stable_id: input.stableId }
        : {}),
    ...(input.topic === "service_request" && input.service ? { service: input.service } : {}),
    ...(input.topic === "country_request" && input.country ? { country: input.country } : {}),
    diagnostics,
    diagnostics_previewed: true,
    vulnerability: input.vulnerability,
    ...(input.errorCode ? { error_code: input.errorCode } : {}),
    subject: input.subject ?? "",
    message: input.message ?? "",
    evidence: input.evidence ?? "",
    ...(input.authorAccountId ? { author_account_id: input.authorAccountId } : {}),
    ...(input.recipientAccountId ? { recipient_account_id: input.recipientAccountId } : {}),
    idempotency_key: randomBytes(16).toString("hex"),
  });
  revalidatePath("/[locale]/reports", "page");
  return { caseId: result.body.case_id, operationId: result.operationId };
}
