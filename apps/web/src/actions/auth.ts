"use server";

import { redirect } from "next/navigation";

import { asAccountId, asDeviceId } from "@/lib/brands";
import {
  clearSessionCookies,
  createCsrfToken,
  createSessionToken,
  setSessionCookies,
} from "@/lib/auth/session";
import { FIXTURE_ACCOUNT_ID, FIXTURE_DEVICE_ID } from "@/mocks/fixtures";

export type LoginProvider = "google" | "github";

function redirectTo(path: string): never {
  redirect(path);
}

/**
 * Mock-first OAuth start (ADR-0041). Real #80 exchange will replace the body;
 * the web only drives UX and never holds long-lived provider tokens.
 */
export async function startLoginAction(
  provider: LoginProvider,
  options: { returnTo?: string; locale?: string } = {},
) {
  // Mock success path: establish opaque server session immediately.
  const accountId = asAccountId(FIXTURE_ACCOUNT_ID);
  const deviceId = asDeviceId(FIXTURE_DEVICE_ID);
  const { token } = createSessionToken(accountId, deviceId);
  const csrf = createCsrfToken();
  await setSessionCookies(token, csrf);
  const locale = options.locale === "en" || options.locale === "ru" ? options.locale : "ru";
  const fallback = `/${locale}/account`;
  const target =
    options.returnTo && options.returnTo.startsWith(`/${locale}/`)
      ? options.returnTo
      : options.returnTo && options.returnTo.startsWith("/")
        ? `/${locale}${options.returnTo}`
        : fallback;
  // Provider is recorded only for UX parity tests; tokens never stored client-side.
  void provider;
  redirectTo(target);
}

export async function logoutAction(locale = "ru") {
  await clearSessionCookies();
  redirectTo(`/${locale}/login`);
}

export async function mockLoginErrorAction(locale = "ru") {
  await Promise.resolve();
  redirectTo(`/${locale}/login?status=error`);
}

export async function mockLoginCancelAction(locale = "ru") {
  await Promise.resolve();
  redirectTo(`/${locale}/login?status=cancel`);
}
