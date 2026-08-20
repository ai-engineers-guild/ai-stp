import { afterEach, describe, expect, it, vi } from "vitest";

const jar = {
  get: vi.fn<(name: string) => { value: string } | undefined>(),
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

describe("session isolation", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    jar.get.mockReset();
  });

  it("does not share private request cookies across two session contexts", async () => {
    stubEnv();
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      () =>
        Promise.resolve(
          new Response(JSON.stringify({ schema_version: 1 }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { privateApiRequest } = await import("@/lib/api/http");
    await privateApiRequest("/v1/account", { sessionToken: "session-a" });
    await privateApiRequest("/v1/account", { sessionToken: "session-b" });

    const firstInit = fetchMock.mock.calls[0]?.[1];
    const secondInit = fetchMock.mock.calls[1]?.[1];
    expect(firstInit).toBeDefined();
    expect(secondInit).toBeDefined();
    if (!firstInit || !secondInit) {
      throw new Error("missing fetch init");
    }
    const first = new Headers(firstInit.headers);
    const second = new Headers(secondInit.headers);
    expect(first.get("cookie")).toContain("session-a");
    expect(first.get("cookie")).not.toContain("session-b");
    expect(second.get("cookie")).toContain("session-b");
    expect(second.get("cookie")).not.toContain("session-a");
    expect(first.get("cookie")).not.toBe(second.get("cookie"));
  });

  it("does not attach a nearby session cookie to a public catalog GET", async () => {
    stubEnv();
    jar.get.mockImplementation((name: string) =>
      name === "ai_stp_session" ? { value: "session-a" } : undefined,
    );
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      () =>
        Promise.resolve(
          new Response(JSON.stringify({ schema_version: 1, items: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { publicApiGet } = await import("@/lib/api/public-http");
    await publicApiGet("/v1/catalog/services");

    const init = fetchMock.mock.calls[0]?.[1];
    expect(init).toBeDefined();
    if (!init) {
      throw new Error("missing fetch init");
    }
    const headers = new Headers(init.headers);
    expect(headers.get("cookie")).toBeNull();
    expect(jar.get).not.toHaveBeenCalled();
  });
});
