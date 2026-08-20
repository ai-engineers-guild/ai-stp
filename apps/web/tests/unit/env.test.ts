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
  });
});
