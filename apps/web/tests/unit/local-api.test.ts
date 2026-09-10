// @vitest-environment node
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

const values = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) => {
        const value = values.get(name);
        return value ? { value } : undefined;
      },
    }),
}));

describe("real on-demand local API from Web", () => {
  afterEach(() => {
    values.clear();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    vi.resetModules();
  });

  it("uses a disposable loopback process offline and requires mutation CSRF", async () => {
    vi.stubEnv(
      "AI_STP_LOCAL_PYTHON",
      path.resolve(
        "../..",
        process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python",
      ),
    );
    vi.stubEnv("AI_STP_USE_MOCKS", "false");
    vi.stubEnv("AI_STP_MOCK_AUTH", "false");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://unreachable.invalid:1");
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://127.0.0.1:3000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "local-test-secret-at-least-32-characters");
    const originalFetch = globalThis.fetch;
    const network = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = new URL(input instanceof Request ? input.url : String(input));
      if (url.hostname !== "127.0.0.1") throw new Error("Network disabled outside loopback");
      return originalFetch(input, init);
    });
    const { startLocalSession, stopLocalSession, localSessionFor } =
      await import("@/lib/local-api");
    const session = await startLocalSession();
    try {
      expect(await startLocalSession(session.session)).toEqual(session);
      values.set("ai_stp_product_mode", "local");
      values.set("ai_stp_local_session", session.session);
      values.set("ai_stp_local_csrf", session.csrf);
      values.set("ai_stp_session", "remote-secret-must-not-leak");
      const { privateApiRequest, apiRequestWithMeta } = await import("@/lib/api/http");
      const context = await privateApiRequest<{ mode: string }>("/v1/context");
      expect(context.mode).toBe("local");
      expect((await apiRequestWithMeta<{ mode: string }>("/v1/context")).data.mode).toBe("local");
      const unauthenticated = await originalFetch(session.api_base_url + "/v1/context");
      expect(unauthenticated.status).toBe(401);
      for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
        const denied = await originalFetch(session.api_base_url + "/v1/local/session", {
          method,
          headers: { "X-AI-STP-Local-Session": session.session },
        });
        expect(denied.status).toBe(403);
      }
      const requests = network.mock.calls.map(([, init]) => JSON.stringify(init?.headers));
      expect(requests.join(" ")).not.toContain("remote-secret-must-not-leak");
    } finally {
      await stopLocalSession(session.session, session.csrf);
    }
    expect(localSessionFor(session.session)).toBeUndefined();
    await expect(originalFetch(session.api_base_url + "/v1/context")).rejects.toThrow();
    const { privateApiRequest } = await import("@/lib/api/http");
    await expect(privateApiRequest("/v1/context")).rejects.toMatchObject({
      code: "AI_STP_UNAVAILABLE",
    });
  }, 45_000);
});
