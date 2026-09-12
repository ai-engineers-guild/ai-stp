"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";

import { ApiError } from "@/lib/api/errors";
import { privateApiRequest, type PrivateRequestOptions } from "@/lib/api/http";
import { assertCsrf, readCsrfToken, readSession, SESSION_COOKIE } from "@/lib/auth/session";

import type { CorporateAuditExport, CorporateContext } from "@/lib/api/generated/types.gen";

type CorporateMutation = {
  csrfToken: string;
  organizationId: string;
  path: string;
  method: "POST" | "PUT" | "PATCH" | "DELETE";
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
    revalidatePath("/[locale]/corporate", "layout");
    return { ok: true, data };
  } catch (error) {
    return { ok: false, message: error instanceof ApiError ? error.message : "request failed" };
  }
}

export async function corporateTeamAssignmentsAction(input: {
  csrfToken: string;
  organizationId: string;
  assignments: Array<{
    accountId: string;
    teamId: string;
    role: "staff" | "lead";
    operation: "assign" | "remove";
    idempotencyKey: string;
  }>;
}): Promise<{ completed: string[]; message?: string }> {
  const completed: string[] = [];
  if (
    !/^organization_[A-Za-z0-9_-]{20,80}$/.test(input.organizationId) ||
    !input.assignments.length ||
    input.assignments.length > 256
  ) {
    return { completed, message: "invalid corporate target" };
  }
  try {
    assertCsrf(input.csrfToken, await readCsrfToken());
    if (!(await readSession())) return { completed, message: "not signed in" };
    const sessionToken = (await cookies()).get(SESSION_COOKIE)?.value;
    if (!sessionToken) return { completed, message: "not signed in" };
    const path = `/v1/corporate/organizations/${input.organizationId}`;
    for (const assignment of input.assignments) {
      const context = await privateApiRequest<CorporateContext>(`${path}/context`, {
        sessionToken,
      });
      await privateApiRequest(`${path}/membership-assignments`, {
        sessionToken,
        method: "POST",
        body: {
          schema_version: 1,
          account_id: assignment.accountId,
          team_id: assignment.teamId,
          team_role: assignment.role,
          operation: assignment.operation,
          authorization_revision: context.organization.authorization_revision,
          idempotency_key: assignment.idempotencyKey,
        },
      });
      completed.push(assignment.idempotencyKey);
    }
    return { completed };
  } catch (error) {
    return { completed, message: error instanceof ApiError ? error.message : "request failed" };
  } finally {
    revalidatePath("/[locale]/corporate", "layout");
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
