"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";

import { ApiError } from "@/lib/api/errors";
import { privateApiRequest, type PrivateRequestOptions } from "@/lib/api/http";
import { assertCsrf, readCsrfToken, readSession, SESSION_COOKIE } from "@/lib/auth/session";

import type {
  CorporateAuditExport,
  CorporateContext,
  TechnologyMergePlanView,
  ProjectTechnologyView,
  SetupListResponse,
  ComponentListResponse,
  SetupDetail,
  ComponentDetail,
} from "@/lib/api/generated/types.gen";

type CorporateMutation = {
  csrfToken: string;
  organizationId: string;
  path: string;
  method: "POST" | "PUT" | "PATCH" | "DELETE";
  body: unknown;
};

type MutationResult = { ok: true; data: unknown } | { ok: false; message: string };

type AuditExportResult = { ok: true; data: CorporateAuditExport } | { ok: false; message: string };

export async function corporateCatalogSearchAction(input: {
  kind: string;
  query: string;
  csrfToken: string;
}): Promise<{ ok: true; items: { id: string; name: string }[] } | { ok: false; message: string }> {
  try {
    assertCsrf(input.csrfToken, await readCsrfToken());
    if (!(await readSession())) return { ok: false, message: "not signed in" };
    if ((input.kind !== "setup" && input.kind !== "component") || input.query.length > 200)
      return { ok: false, message: "invalid catalog search" };
    const sessionToken = (await cookies()).get(SESSION_COOKIE)?.value;
    const options = {
      ...(sessionToken ? { sessionToken } : {}),
      query: { q: input.query, page_size: 32, include_experimental: true },
    };
    const result =
      input.kind === "setup"
        ? await privateApiRequest<SetupListResponse>("/v1/catalog/setups", options)
        : await privateApiRequest<ComponentListResponse>("/v1/catalog/components", options);
    return {
      ok: true,
      items: [...result.items, ...result.experimental].map((item) => ({
        id: item.stable_id,
        name: item.latest_name,
      })),
    };
  } catch (error) {
    return { ok: false, message: error instanceof ApiError ? error.message : "request failed" };
  }
}

export async function corporateCatalogVersionsAction(input: {
  kind: string;
  id: string;
  csrfToken: string;
}): Promise<{ ok: true; versions: string[] } | { ok: false; message: string }> {
  try {
    assertCsrf(input.csrfToken, await readCsrfToken());
    if (!(await readSession())) return { ok: false, message: "not signed in" };
    const validId =
      (input.kind === "setup" && /^setup_[0-9A-HJKMNP-TV-Z]{26}$/.test(input.id)) ||
      (input.kind === "component" && /^component_[0-9A-HJKMNP-TV-Z]{26}$/.test(input.id));
    if (!validId) return { ok: false, message: "invalid catalog target" };
    const sessionToken = (await cookies()).get(SESSION_COOKIE)?.value;
    const result = await privateApiRequest<SetupDetail | ComponentDetail>(
      `/v1/catalog/${input.kind === "setup" ? "setups" : "components"}/${input.id}`,
      sessionToken ? { sessionToken } : {},
    );
    return {
      ok: true,
      versions: result.versions
        .filter((item) => item.lifecycle !== "blocked")
        .map((item) => item.version),
    };
  } catch (error) {
    return { ok: false, message: error instanceof ApiError ? error.message : "request failed" };
  }
}

export async function corporateProjectUsageAction(input: {
  csrfToken: string;
  organizationId: string;
  projectId: string;
  technologyId: string;
}): Promise<{ ok: true; data: ProjectTechnologyView } | { ok: false; message: string }> {
  if (
    !/^organization_[A-Za-z0-9_-]{20,80}$/.test(input.organizationId) ||
    !/^remote_project_[0-9A-HJKMNP-TV-Z]{26}$/.test(input.projectId) ||
    !/^technology_[0-9A-HJKMNP-TV-Z]{26}$/.test(input.technologyId)
  )
    return { ok: false, message: "invalid corporate target" };
  try {
    assertCsrf(input.csrfToken, await readCsrfToken());
    if (!(await readSession())) return { ok: false, message: "not signed in" };
    const sessionToken = (await cookies()).get(SESSION_COOKIE)?.value;
    if (!sessionToken) return { ok: false, message: "not signed in" };
    const data = await privateApiRequest<ProjectTechnologyView>(
      `/v1/corporate/organizations/${input.organizationId}/projects/${input.projectId}/technologies/${input.technologyId}`,
      { sessionToken },
    );
    return { ok: true, data };
  } catch (error) {
    return { ok: false, message: error instanceof ApiError ? error.message : "request failed" };
  }
}

export async function corporateTechnologyMergePlanAction(input: {
  csrfToken: string;
  organizationId: string;
  sourceId: string;
  targetId: string;
}): Promise<{ ok: true; data: TechnologyMergePlanView } | { ok: false; message: string }> {
  if (
    !/^organization_[A-Za-z0-9_-]{20,80}$/.test(input.organizationId) ||
    ![input.sourceId, input.targetId].every((id) => /^technology_[0-9A-HJKMNP-TV-Z]{26}$/.test(id))
  )
    return { ok: false, message: "invalid corporate target" };
  try {
    assertCsrf(input.csrfToken, await readCsrfToken());
    if (!(await readSession())) return { ok: false, message: "not signed in" };
    const sessionToken = (await cookies()).get(SESSION_COOKIE)?.value;
    if (!sessionToken) return { ok: false, message: "not signed in" };
    const data = await privateApiRequest<TechnologyMergePlanView>(
      `/v1/corporate/organizations/${input.organizationId}/technologies/${input.sourceId}/merge-plan`,
      { sessionToken, query: { target_id: input.targetId } },
    );
    return { ok: true, data };
  } catch (error) {
    return { ok: false, message: error instanceof ApiError ? error.message : "request failed" };
  }
}

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
