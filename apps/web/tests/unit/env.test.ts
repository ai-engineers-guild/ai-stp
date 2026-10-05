import { afterEach, describe, expect, it, vi } from "vitest";

describe("getEnv", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
  });

  it("fails loud when required vars are missing", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "");
    vi.stubEnv("AI_STP_API_BASE_URL", "");
    vi.stubEnv("AI_STP_SESSION_SECRET", "short");
    vi.stubEnv("AI_STP_USE_MOCKS", "false");
    const mod = await import("@/lib/env");
    mod.resetEnvCache();
    expect(() => mod.getEnv()).toThrow(/Invalid apps\/web environment/);
  });

  it("parses a valid environment", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USE_MOCKS", "true");
    const mod = await import("@/lib/env");
    mod.resetEnvCache();
    const env = mod.getEnv();
    expect(env.AI_STP_USE_MOCKS).toBe(true);
    expect(env.AI_STP_API_BASE_URL).toBe("http://localhost:8000");
    expect(env.AI_STP_USER_DOCS_URL).toBe("http://localhost:8011");
    expect(env.AI_STP_AUTH_SSO_PROVIDERS).toEqual([]);
    expect(env.AI_STP_AUTH_PROVIDERS).toEqual(["google", "github"]);
  });

  it("parses the corporate SSO provider list", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_AUTH_SSO_PROVIDERS", " authentik, keycloak, gitlab ");
    const mod = await import("@/lib/env");
    mod.resetEnvCache();
    expect(mod.getEnv().AI_STP_AUTH_SSO_PROVIDERS).toEqual(["authentik", "keycloak", "gitlab"]);
  });

  it("rejects an unknown SSO provider name", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_AUTH_SSO_PROVIDERS", "authentik,okta");
    const mod = await import("@/lib/env");
    mod.resetEnvCache();
    expect(() => mod.getEnv()).toThrow(/Invalid apps\/web environment/);
  });

  it("parses a primary sign-in provider list with gitlab instead of github", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_AUTH_PROVIDERS", " google , gitlab ");
    const mod = await import("@/lib/env");
    mod.resetEnvCache();
    expect(mod.getEnv().AI_STP_AUTH_PROVIDERS).toEqual(["google", "gitlab"]);
  });

  it("hides primary buttons on an explicit empty sign-in list", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_AUTH_PROVIDERS", "");
    const mod = await import("@/lib/env");
    mod.resetEnvCache();
    expect(mod.getEnv().AI_STP_AUTH_PROVIDERS).toEqual([]);
  });

  it("rejects an unknown sign-in provider name", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_AUTH_PROVIDERS", "github,okta");
    const mod = await import("@/lib/env");
    mod.resetEnvCache();
    expect(() => mod.getEnv()).toThrow(/Invalid apps\/web environment/);
  });
});
