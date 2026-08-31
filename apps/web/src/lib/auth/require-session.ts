import { cache } from "react";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { readSession, type WebSession, SESSION_COOKIE } from "@/lib/auth/session";

/**
 * Server-side session gate. Expired/invalid sessions redirect to login with a
 * session_expired reason and never expose protected data (REQ-2301, REQ-2308).
 *
 * Cookies are never mutated during render (Next.js forbids it outside a Server
 * Action or Route Handler). A stale cookie is cleared by the logout route
 * handler, which is allowed to modify cookies.
 */
export async function requireSession(locale: string, returnTo: string): Promise<WebSession> {
  const session = await readSession();
  if (session) {
    if (session.accountStatus === "onboarding_pending") {
      redirect(`/${locale}/onboarding?${new URLSearchParams({ returnTo }).toString()}`);
    }
    return session;
  }
  const jar = await cookies();
  const hadCookie = Boolean(jar.get(SESSION_COOKIE)?.value);
  if (hadCookie) {
    // Stale/invalid cookie: clear it in the logout route handler, then land on
    // login with the expiry reason preserved.
    const params = new URLSearchParams({ locale, returnTo, reason: "session_expired" });
    redirect(`/api/auth/logout?${params.toString()}`);
  }
  redirect(`/${locale}/login?${new URLSearchParams({ returnTo }).toString()}`);
}

/** Session gate for the legal-onboarding screen itself. */
export async function requireOnboardingSession(
  locale: string,
  returnTo: string,
): Promise<WebSession> {
  const session = await readSession();
  if (!session) {
    const jar = await cookies();
    if (jar.get(SESSION_COOKIE)?.value) {
      const params = new URLSearchParams({ locale, returnTo, reason: "session_expired" });
      redirect(`/api/auth/logout?${params.toString()}`);
    }
    redirect(`/${locale}/login?${new URLSearchParams({ returnTo }).toString()}`);
  }
  if (session.accountStatus === "active") {
    redirect(returnTo);
  }
  return session;
}

export const getOptionalSession = cache(async (): Promise<WebSession | null> => {
  // Read-only: never mutate cookies during render. A stale cookie is harmless
  // here and is cleared on the next protected-route visit or at login.
  return readSession();
});

/** Cookie presence only — for chrome/nav; no /v1/auth/me. */
export const hasSessionCookie = cache(async (): Promise<boolean> => {
  const jar = await cookies();
  return Boolean(jar.get(SESSION_COOKIE)?.value);
});

export function sessionCookieValue(): Promise<string | undefined> {
  return cookies().then((jar) => jar.get(SESSION_COOKIE)?.value);
}
