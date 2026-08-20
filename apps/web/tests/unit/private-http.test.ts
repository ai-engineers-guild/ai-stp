import { afterEach, describe, expect, it, vi } from "vitest";

const jar = {
  get: vi.fn((name: string) => {
    if (name === "ai_stp_session") return { value: "session-fixture" };
    if (name === "ai_stp_csrf") return { value: "csrf-fixture" };
    return undefined;
  }),
};

vi.mock("next/headers", () => ({
  cookies: vi.fn(() => Promise.resolve(jar)),
}));

function stubEnv(): void {
  vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
  vi.stubEnv("AI_STP_API_BASE_URL", "http://api.test:8000");
  vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
  vi.stubEnv("AI_STP_USE_MOCKS", "false");
  vi.stubEnv("AI_STP_MOCK_AUTH", "false");
}

describe("private request helpers", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    jar.get.mockClear();
  });

  it("keeps no-store on private GET, mutation, binary, and meta paths", async () => {
    stubEnv();
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      () =>
        Promise.resolve(
          new Response(JSON.stringify({ ok: true }), {
            status: 200,
            headers: { "Content-Type": "application/json", "x-operation-id": "op_fixture" },
          }),
        ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { privateApiRequest, apiRequestBinary, apiRequestWithMeta } =
      await import("@/lib/api/http");
    await privateApiRequest("/v1/account", { sessionToken: "session-a" });
    await privateApiRequest("/v1/account/privacy", {
      method: "PUT",
      sessionToken: "session-a",
      body: { allow_publisher_listing: true },
    });
    await apiRequestWithMeta("/v1/reports", {
      method: "POST",
      sessionToken: "session-a",
      body: { schema_version: 1 },
    });
    await apiRequestBinary("/v1/account/public-profile/avatar", {
      method: "POST",
      sessionToken: "session-a",
      contentType: "image/png",
      body: new Uint8Array([1, 2, 3]),
    });

    expect(fetchMock).toHaveBeenCalledTimes(4);
    for (const call of fetchMock.mock.calls) {
      const init = call[1];
      expect(init).toBeDefined();
      if (!init) {
        throw new Error("missing fetch init");
      }
      expect(init.cache).toBe("no-store");
      expect(init).not.toHaveProperty("next");
    }
  });
});
