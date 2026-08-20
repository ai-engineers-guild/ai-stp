"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import { CSRF_COOKIE, SESSION_COOKIE } from "@/lib/auth/cookies";
import { assertCsrf, readCsrfToken, readSession } from "@/lib/auth/session";

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
    redirect(`${resultPath}?status=error`);
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
    if (error instanceof ApiError) {
      redirect(`${resultPath}?status=error&user_code=${encodeURIComponent(input.userCode)}`);
    }
    redirect(`${resultPath}?status=error`);
  }
  redirect(`${resultPath}?status=ok`);
}
