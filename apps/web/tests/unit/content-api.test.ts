import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({
  cookies: vi.fn(() => {
    throw new Error("public GET must not read cookies()");
  }),
}));

function stubEnv(): void {
  vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
  vi.stubEnv("AI_STP_API_BASE_URL", "http://api.test:8000");
  vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
  vi.stubEnv("AI_STP_USE_MOCKS", "false");
  vi.stubEnv("AI_STP_MOCK_AUTH", "false");
}

// Production logged a server error for every crawl of `/ai/content/...`: the
// page metadata asked the API for locale `ai`, and the API answered 400.
describe("content API for a locale the site does not serve", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("answers without a request", async () => {
    stubEnv();
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>();
    vi.stubGlobal("fetch", fetchMock);

    const { listPublishedContent, readPublishedContent } = await import("@/lib/api/content");

    await expect(readPublishedContent("ai", "blog_post", "vibe-coding-safety")).resolves.toBeNull();
    await expect(listPublishedContent("ai")).resolves.toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("still asks the API for a served locale", async () => {
    stubEnv();
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      () =>
        Promise.resolve(
          new Response(JSON.stringify({ schema_version: 1, etag: "e", items: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { listPublishedContent } = await import("@/lib/api/content");

    await expect(listPublishedContent("en")).resolves.toEqual([]);
    expect(fetchMock).toHaveBeenCalledOnce();
    const requested = fetchMock.mock.calls[0]?.[0];
    expect(requested instanceof URL ? requested.href : requested).toContain("locale=en");
  });
});
