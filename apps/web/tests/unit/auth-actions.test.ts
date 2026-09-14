import { afterEach, describe, expect, it, vi } from "vitest";
import type * as AuthModule from "@/actions/auth";

const redirect = vi.fn((url: string) => {
  throw new Error(`REDIRECT:${url}`);
});
const setSessionCookies = vi.fn();
type AuthActions = typeof AuthModule;

vi.mock("next/navigation", () => ({ redirect }));
vi.mock("@/lib/auth/session", () => ({
  clearSessionCookies: vi.fn(),
  createCsrfToken: vi.fn(),
  createSessionToken: vi.fn(),
  setSessionCookies,
}));

describe("auth actions", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
    redirect.mockClear();
    setSessionCookies.mockClear();
  });

  function stubEnv(useMocks: boolean): void {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USE_MOCKS", String(useMocks));
  }

  it.each([
    [
      "startLoginAction",
      async (auth: AuthActions) => auth.startLoginAction("github", { locale: "en" }),
    ],
    ["mockLoginErrorAction", async (auth: AuthActions) => auth.mockLoginErrorAction("en")],
    ["mockLoginCancelAction", async (auth: AuthActions) => auth.mockLoginCancelAction("en")],
  ])("rejects %s outside mock mode without creating a session", async (_name, invoke) => {
    stubEnv(false);
    const auth = await import("@/actions/auth");
    await expect(invoke(auth)).rejects.toThrow("REDIRECT:/en/login?status=error");
    expect(setSessionCookies).not.toHaveBeenCalled();
  });
});
