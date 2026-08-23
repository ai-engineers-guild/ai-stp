"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ApiError, type ApiErrorCode } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import { CSRF_COOKIE, SESSION_COOKIE } from "@/lib/auth/cookies";
import { assertCsrf, readCsrfToken, readSession } from "@/lib/auth/session";

/**
 * Which refusal the reader is looking at, keyed by what the platform answered.
 *
 * `unknown` and `expired` are the two a person actually hits, and they need
 * opposite responses: retype the code, or ask the CLI for a new one.
 */
const REASONS: Partial<Record<ApiErrorCode, string>> = {
  AI_STP_NOT_FOUND: "unknown",
  AI_STP_VALIDATION_ERROR: "expired",
  AI_STP_CONFLICT: "resolved",
};

export async function approveDeviceCodeAction(input: {
  userCode: string;
  csrfToken: string;
  locale: string;
  destination?: "device-login" | "devices";
}): Promise<void> {
  const destination = input.destination ?? "device-login";
  const resultPath = `/${input.locale}/${destination}`;
  const cookieCsrf = await readCsrfToken();
  try {
    assertCsrf(input.csrfToken, cookieCsrf);
  } catch {
    redirect(`${resultPath}?status=error&reason=csrf`);
  }
  const session = await readSession();
  if (!session) {
    redirect(`/${input.locale}/login?returnTo=${encodeURIComponent(resultPath)}`);
  }
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) {
    redirect(`/${input.locale}/login?returnTo=${encodeURIComponent(resultPath)}`);
  }
  const csrfHeader = jar.get(CSRF_COOKIE)?.value;
  try {
    await apiRequest("/v1/auth/device/approve", {
      method: "POST",
      sessionToken: token,
      body: { user_code: input.userCode.trim().toUpperCase() },
      headers: csrfHeader ? { "X-CSRF-Token": csrfHeader } : {},
    });
  } catch (error) {
    // The platform distinguishes four refusals — unknown code, expired,
    // already resolved, and a rejected request — and every one of them used to
    // arrive here as the bare word "error". Someone approving a device could
    // not tell a code that had timed out from one they mistyped, which is the
    // difference between retrying and re-running `ai-stp auth login`.
    if (error instanceof ApiError) {
      const reason = REASONS[error.code] ?? "failed";
      redirect(
        `${resultPath}?status=error&reason=${reason}&user_code=${encodeURIComponent(input.userCode)}`,
      );
    }
    redirect(`${resultPath}?status=error&reason=failed`);
  }
  redirect(`${resultPath}?status=ok`);
}
