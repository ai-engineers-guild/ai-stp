import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * requireSession must never render protected content for missing/stale cookies
 * (SPEC-023 REQ-2301, REQ-2308). Cookie clear happens on the logout route.
 */

const cookieStore = {
  get: vi.fn(),
};

const redirect = vi.fn((url: string) => {
  throw new Error(`REDIRECT:${url}`);
});

vi.mock("next/headers", () => ({
  cookies: vi.fn(() => Promise.resolve(cookieStore)),
}));

vi.mock("next/navigation", () => ({
  redirect: (url: string) => redirect(url),
}));

describe("requireSession", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
    cookieStore.get.mockReset();
    redirect.mockClear();
  });

  function stubEnv(): void {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USE_MOCKS", "true");
  }

  it("redirects anonymous visitors to login with returnTo", async () => {
    stubEnv();
    cookieStore.get.mockReturnValue(undefined);
    const { requireSession } = await import("@/lib/auth/require-session");
    await expect(requireSession("en", "/en/devices")).rejects.toThrow(
      "REDIRECT:/en/login?returnTo=%2Fen%2Fdevices",
    );
  });

  it("sends stale cookies through logout so they are cleared", async () => {
    stubEnv();
    // Cookie present but mock session cannot parse it as a valid session.
    cookieStore.get.mockReturnValue({ value: "not-a-valid-session-token" });
    const { requireSession } = await import("@/lib/auth/require-session");
    await expect(requireSession("ru", "/ru/account")).rejects.toThrow(
      /REDIRECT:\/api\/auth\/logout/,
    );
    const call = redirect.mock.calls[0]?.[0] ?? "";
    expect(call).toContain("locale=ru");
    expect(call).toContain("reason=session_expired");
    expect(call).toContain("returnTo=");
  });

  it("returns the session when a valid mock token is present", async () => {
    stubEnv();
    const { createSessionToken, SESSION_COOKIE } = await import("@/lib/auth/session");
    const { asAccountId } = await import("@/lib/brands");
    const { token, session } = createSessionToken(
      asAccountId("account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"),
    );
    cookieStore.get.mockImplementation((name: string) =>
      name === SESSION_COOKIE ? { value: token } : undefined,
    );
    // readSession in mock mode uses the cookie HMAC path.
    const { requireSession } = await import("@/lib/auth/require-session");
    const resolved = await requireSession("en", "/en/devices");
    expect(resolved.accountId).toBe(session.accountId);
    expect(redirect).not.toHaveBeenCalled();
  });
});
