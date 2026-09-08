"use server";

import { cookies } from "next/headers";
import { privateApiRequest } from "@/lib/api/http";
import { ApiError } from "@/lib/api/errors";
import { assertCsrf, readCsrfToken, readSession, SESSION_COOKIE } from "@/lib/auth/session";
import type {
  GitHubConnectorStatus,
  GitHubConnectRequest,
  GitHubConnectResponse,
  GitHubDisconnectRequest,
  GitHubSourcePrepareRequest,
  GitHubSourcePrepared,
  GitHubActionPlanRequest,
  GitHubActionPlanResponse,
  GitHubActionConfirmRequest,
  VisibilityPlanCreateRequest,
  VisibilityPlanResponse,
  VisibilityConfirmRequest,
} from "@/lib/api/generated/types.gen";

type Result<T> = { ok: true; data: T } | { ok: false; code: string; reason?: string };

async function request<T>(csrf: string, path: string, body?: unknown): Promise<Result<T>> {
  try {
    assertCsrf(csrf, await readCsrfToken());
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

export async function githubStatus(csrf: string) {
  return request<GitHubConnectorStatus>(csrf, "/v1/connectors/github");
}
export async function githubConnect(csrf: string, body: GitHubConnectRequest) {
  return request<GitHubConnectResponse>(csrf, "/v1/connectors/github/connect", body);
}
export async function githubDisconnect(csrf: string, body: GitHubDisconnectRequest) {
  return request<GitHubConnectorStatus>(csrf, "/v1/connectors/github/disconnect", body);
}
export async function githubPrepare(csrf: string, body: GitHubSourcePrepareRequest) {
  return request<GitHubSourcePrepared>(csrf, "/v1/connectors/github/sources", body);
}
export async function githubPlan(csrf: string, body: GitHubActionPlanRequest) {
  return request<GitHubActionPlanResponse>(csrf, "/v1/connectors/github/actions", body);
}
export async function githubActionStatus(csrf: string, planId: string) {
  return request<GitHubActionPlanResponse>(csrf, `/v1/connectors/github/actions/${encodeURIComponent(planId)}`);
}
export async function githubConfirm(
  csrf: string,
  planId: string,
  body: GitHubActionConfirmRequest,
) {
  return request<GitHubActionPlanResponse>(
    csrf,
    `/v1/connectors/github/actions/${encodeURIComponent(planId)}/confirm`,
    body,
  );
}
export async function visibilityPlan(csrf: string, body: VisibilityPlanCreateRequest) {
  return request<VisibilityPlanResponse>(csrf, "/v1/access/visibility/plans", body);
}
export async function visibilityConfirm(
  csrf: string,
  planId: string,
  body: VisibilityConfirmRequest,
) {
  return request<VisibilityPlanResponse>(
    csrf,
    `/v1/access/visibility/plans/${encodeURIComponent(planId)}/confirm`,
    body,
  );
}
