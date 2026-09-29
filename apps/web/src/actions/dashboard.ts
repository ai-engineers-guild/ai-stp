"use server";

import { getTranslations } from "next-intl/server";

import { ApiError } from "@/lib/api/errors";
import { readCorporateContext } from "@/lib/api/corporate";
import { privateApiRequest } from "@/lib/api/http";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { readSession, requireCsrf } from "@/lib/auth/session";
import type {
  DashboardQuery,
  DashboardResult,
  DashboardView,
  DashboardViewList,
  DashboardViewRequest,
} from "@/lib/api/generated/types.gen";

type Result<T> = { ok: true; data: T } | { ok: false; message: string };

class ContextError extends Error {
  constructor(readonly key: "notSignedIn" | "noOrganization") {
    super(key);
  }
}

async function context(csrfToken: string) {
  await requireCsrf(csrfToken);
  if (!(await readSession())) throw new ContextError("notSignedIn");
  const token = await sessionCookieValue();
  if (!token) throw new ContextError("notSignedIn");
  const value = await readCorporateContext(token);
  if (!value) throw new ContextError("noOrganization");
  return { value, token };
}

async function failure(error: unknown): Promise<{ ok: false; message: string }> {
  if (error instanceof ApiError) return { ok: false, message: error.message };
  const common = await getTranslations("common");
  if (error instanceof ContextError) {
    if (error.key === "noOrganization") {
      const corporate = await getTranslations("corporate");
      return { ok: false, message: corporate("noOrganization") };
    }
    return { ok: false, message: common("notSignedIn") };
  }
  return { ok: false, message: common("requestFailed") };
}

export async function queryDashboardAction(input: {
  csrfToken: string;
  query: DashboardQuery;
}): Promise<Result<DashboardResult>> {
  try {
    const { value: current, token } = await context(input.csrfToken);
    const data = await privateApiRequest<DashboardResult>(
      `/v1/corporate/organizations/${current.organization.organization_id}/dashboard/query`,
      { sessionToken: token, method: "POST", body: { query: input.query } },
    );
    return { ok: true, data };
  } catch (error) {
    return failure(error);
  }
}

export async function listDashboardViewsAction(input: {
  csrfToken: string;
}): Promise<Result<DashboardViewList>> {
  try {
    const { value: current, token } = await context(input.csrfToken);
    const data = await privateApiRequest<DashboardViewList>(
      `/v1/corporate/organizations/${current.organization.organization_id}/dashboard/views`,
      { sessionToken: token },
    );
    return { ok: true, data };
  } catch (error) {
    return failure(error);
  }
}

export async function saveDashboardViewAction(input: {
  csrfToken: string;
  name: string;
  scope: DashboardViewRequest["scope"];
  scopeId: string;
  query: DashboardQuery;
  viewId?: string;
  expectedRevision?: number;
  idempotencyKey: string;
}): Promise<Result<DashboardView>> {
  try {
    const { value: current, token } = await context(input.csrfToken);
    const path = `/v1/corporate/organizations/${current.organization.organization_id}/dashboard/views`;
    const body: DashboardViewRequest = {
      name: input.name,
      scope: input.scope,
      scope_id: input.scopeId,
      query: input.query,
      authorization_revision: current.organization.authorization_revision,
      expected_revision: input.expectedRevision ?? 0,
      idempotency_key: input.idempotencyKey,
    };
    const data = await privateApiRequest<DashboardView>(
      input.viewId ? `${path}/${input.viewId}` : path,
      { sessionToken: token, method: input.viewId ? "PUT" : "POST", body },
    );
    return { ok: true, data };
  } catch (error) {
    return failure(error);
  }
}
