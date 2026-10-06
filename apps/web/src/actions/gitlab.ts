"use server";

import { cookies } from "next/headers";
import { privateApiRequest } from "@/lib/api/http";
import { ApiError } from "@/lib/api/errors";
import { readSession, requireCsrf, SESSION_COOKIE } from "@/lib/auth/session";
import type {
  GitLabConnectorStatus,
  GitLabConnectRequest,
  GitLabConnectResponse,
  GitLabDisconnectRequest,
  GitLabActionPlanRequest,
  GitLabActionPlanResponse,
  GitLabActionConfirmRequest,
} from "@/lib/api/generated/types.gen";

type Result<T> = { ok: true; data: T } | { ok: false; code: string; reason?: string };

async function request<T>(csrf: string, path: string, body?: unknown): Promise<Result<T>> {
  try {
    await requireCsrf(csrf);
    if (!(await readSession())) return { ok: false, code: "AI_STP_UNAUTHORIZED" };
    const sessionToken = (await cookies()).get(SESSION_COOKIE)?.value;
    if (!sessionToken) return { ok: false, code: "AI_STP_UNAUTHORIZED" };
    return {
      ok: true,
      data: await privateApiRequest<T>(path, {
        method: body === undefined ? "GET" : "POST",
        body,
        sessionToken,
      }),
    };
  } catch (error) {
    const reason = error instanceof ApiError ? error.details["reason"] : undefined;
    return {
      ok: false,
      code: error instanceof ApiError ? error.code : "AI_STP_UNAVAILABLE",
      ...(typeof reason === "string" && /^[a-z_]{1,64}$/.test(reason) ? { reason } : {}),
    };
  }
}

function base(organizationId: string): string {
  return `/v1/corporate/organizations/${encodeURIComponent(organizationId)}/gitlab`;
}

export async function gitlabStatus(csrf: string, organizationId: string) {
  return request<GitLabConnectorStatus>(csrf, `${base(organizationId)}/connection`);
}
export async function gitlabConnect(
  csrf: string,
  organizationId: string,
  body: GitLabConnectRequest,
) {
  return request<GitLabConnectResponse>(csrf, `${base(organizationId)}/connect`, body);
}
export async function gitlabDisconnect(
  csrf: string,
  organizationId: string,
  body: GitLabDisconnectRequest,
) {
  return request<GitLabConnectorStatus>(
    csrf,
    `${base(organizationId)}/connection/disconnect`,
    body,
  );
}
export async function gitlabPlan(
  csrf: string,
  organizationId: string,
  body: GitLabActionPlanRequest,
) {
  return request<GitLabActionPlanResponse>(csrf, `${base(organizationId)}/actions`, body);
}
export async function gitlabConfirm(
  csrf: string,
  organizationId: string,
  planId: string,
  body: GitLabActionConfirmRequest,
) {
  return request<GitLabActionPlanResponse>(
    csrf,
    `${base(organizationId)}/actions/${encodeURIComponent(planId)}/confirm`,
    body,
  );
}
