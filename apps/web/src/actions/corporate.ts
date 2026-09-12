"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";

import { ApiError } from "@/lib/api/errors";
import { privateApiRequest, type PrivateRequestOptions } from "@/lib/api/http";
import { assertCsrf, readCsrfToken, readSession, SESSION_COOKIE } from "@/lib/auth/session";

import type { CorporateAuditExport } from "@/lib/api/generated/types.gen";

type CorporateMutation = {
  csrfToken: string;
  organizationId: string;
  path: string;
  method: "POST" | "PATCH" | "DELETE";
  body: unknown;
};

type MutationResult = { ok: true; data: unknown } | { ok: false; message: string };

type AuditExportResult = { ok: true; data: CorporateAuditExport } | { ok: false; message: string };

export async function corporateMutationAction(input: CorporateMutation): Promise<MutationResult> {
  if (
    !/^organization_[A-Za-z0-9_-]{20,80}$/.test(input.organizationId) ||
    !input.path.startsWith(`/v1/corporate/organizations/${input.organizationId}/`) ||
    input.path.includes("..")
  ) {
    return { ok: false, message: "invalid corporate target" };
  }
  try {
    assertCsrf(input.csrfToken, await readCsrfToken());
    if (!(await readSession())) return { ok: false, message: "not signed in" };
    const sessionToken = (await cookies()).get(SESSION_COOKIE)?.value;
    if (!sessionToken) return { ok: false, message: "not signed in" };
    const options: PrivateRequestOptions = { method: input.method, body: input.body, sessionToken };
    const data = await privateApiRequest<unknown>(input.path, options);
    revalidatePath("/[locale]/corporate", "page");
    return { ok: true, data };
  } catch (error) {
    return { ok: false, message: error instanceof ApiError ? error.message : "request failed" };
  }
}

export async function corporateAuditExportAction(
  organizationId: string,
): Promise<AuditExportResult> {
  if (!/^organization_[A-Za-z0-9_-]{20,80}$/.test(organizationId)) {
    return { ok: false, message: "invalid corporate target" };
  }
  try {
    if (!(await readSession())) return { ok: false, message: "not signed in" };
    const sessionToken = (await cookies()).get(SESSION_COOKIE)?.value;
    if (!sessionToken) return { ok: false, message: "not signed in" };
    const data = await privateApiRequest<CorporateAuditExport>(
      `/v1/corporate/organizations/${organizationId}/audit/export`,
      { sessionToken },
    );
    return { ok: true, data };
  } catch (error) {
    return { ok: false, message: error instanceof ApiError ? error.message : "request failed" };
  }
}
