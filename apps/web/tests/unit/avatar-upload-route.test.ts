import type * as AuthSession from "@/lib/auth/session";

import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth/require-session", () => ({
  sessionCookieValue: vi.fn(() => Promise.resolve("mock-session")),
}));

vi.mock("@/lib/auth/session", async (importOriginal) => ({
  ...(await importOriginal<typeof AuthSession>()),
  readCsrfToken: vi.fn(() => Promise.resolve("test-csrf")),
}));

function stubEnv(): void {
  vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
  vi.stubEnv("AI_STP_API_BASE_URL", "http://api.test:8000");
  vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
  vi.stubEnv("AI_STP_USE_MOCKS", "true");
  vi.stubEnv("AI_STP_MOCK_AUTH", "true");
}

describe("account avatar binary route", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
  });

  it("forwards supported image bytes and returns a persistent asset id", async () => {
    stubEnv();
    const { POST } = await import("@/app/api/account/avatar/route");
    const response = await POST(
      new Request("http://localhost/api/account/avatar", {
        method: "POST",
        headers: { "X-CSRF-Token": "test-csrf", "Content-Type": "image/png" },
        body: new Uint8Array([137, 80, 78, 71]),
      }),
    );

    expect(response.status).toBe(201);
    await expect(response.json()).resolves.toMatchObject({
      avatar_asset_id: "avatar_mock",
      public_url: "/brand/icon-32.png",
    });
  });

  it("rejects missing CSRF before consuming the upload", async () => {
    stubEnv();
    const { POST } = await import("@/app/api/account/avatar/route");
    const request = new Request("http://localhost/api/account/avatar", {
      method: "POST",
      headers: { "Content-Type": "image/png" },
      body: new Uint8Array([1]),
    });
    expect((await POST(request)).status).toBe(403);
    expect(request.bodyUsed).toBe(false);
  });

  it("rejects non-image payloads before forwarding", async () => {
    stubEnv();
    const { POST } = await import("@/app/api/account/avatar/route");
    const response = await POST(
      new Request("http://localhost/api/account/avatar", {
        method: "POST",
        headers: { "X-CSRF-Token": "test-csrf", "Content-Type": "text/plain" },
        body: "not an image",
      }),
    );

    expect(response.status).toBe(400);
  });
});
