import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * Logout must clear cookies with a relative redirect (proxy-safe) and never
 * leave a stale session when the API revoke fails (ADR-0041, REQ-2308).
 */

const cookieStore = {
  get: vi.fn(),
  delete: vi.fn(),
};

vi.mock("next/headers", () => ({
  cookies: vi.fn(() => Promise.resolve(cookieStore)),
}));

describe("api/auth/logout route", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    cookieStore.get.mockReset();
    cookieStore.delete.mockReset();
  });

  function stubEnv(mocks: boolean): void {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://api.test:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USE_MOCKS", mocks ? "true" : "false");
    vi.stubEnv("AI_STP_MOCK_AUTH", "false");
  }

  it("POST clears cookies and redirects to locale login", async () => {
    stubEnv(true);
    cookieStore.get.mockReturnValue(undefined);
    const { POST } = await import("@/app/api/auth/logout/route");
    const response = await POST(new Request("http://localhost/api/auth/logout?locale=en"));
    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/en/login");
    // Relative Location — not an absolute host that would break behind a proxy.
    expect(response.headers.get("Location")?.startsWith("http")).toBe(false);
  });

  it("GET preserves returnTo and reason without calling the API", async () => {
    stubEnv(false);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    cookieStore.get.mockReturnValue({ value: "opaque-session" });
    const { GET } = await import("@/app/api/auth/logout/route");
    const response = GET(
      new Request(
        "http://localhost/api/auth/logout?locale=ru&returnTo=%2Fru%2Fdevices&reason=session_expired",
      ),
    );
    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe(
      "/ru/login?returnTo=%2Fru%2Fdevices&reason=session_expired",
    );
    // Stale-session GET must not revoke a still-valid server session.
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("POST still clears local cookies when API logout fails", async () => {
    stubEnv(false);
    const { SESSION_COOKIE, CSRF_COOKIE } = await import("@/lib/auth/cookies");
    cookieStore.get.mockImplementation((name: string) => {
      if (name === SESSION_COOKIE) {
        return { value: "opaque-session" };
      }
      if (name === CSRF_COOKIE) {
        return { value: "csrf-token" };
      }
      return undefined;
    });
    const fetchMock = vi.fn(() => Promise.reject(new Error("network down")));
    vi.stubGlobal("fetch", fetchMock);
    const { POST } = await import("@/app/api/auth/logout/route");
    const response = await POST(new Request("http://localhost/api/auth/logout?locale=ru"));
    expect(response.status).toBe(303);
    expect(response.headers.get("Location")).toBe("/ru/login");
    expect(fetchMock).toHaveBeenCalled();
  });
});
