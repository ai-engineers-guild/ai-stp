import { readFileSync } from "node:fs";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { PUBLIC_CATALOG_REVALIDATE_SECONDS } from "@/lib/api/cache-policy";

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

describe("publicApiGet", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("does not import next/headers on the public path", () => {
    const root = path.resolve(__dirname, "../../src/lib/api");
    for (const file of ["public-http.ts", "http-shared.ts", "cache-policy.ts"]) {
      const source = readFileSync(path.join(root, file), "utf8");
      expect(source).not.toMatch(/from ["']next\/headers["']/);
      expect(source).not.toMatch(/\bcookies\s*\(/);
    }
  });

  it("sends GET with the short revalidate policy and no credentials", async () => {
    stubEnv();
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

    expect(fetchMock).toHaveBeenCalledOnce();
    const init = fetchMock.mock.calls[0]?.[1] as
      (RequestInit & { next?: { revalidate?: number } }) | undefined;
    expect(init).toBeDefined();
    if (!init) {
      throw new Error("missing fetch init");
    }
    expect(init.method).toBe("GET");
    expect(init.cache).toBe("force-cache");
    expect(init.next).toEqual({ revalidate: PUBLIC_CATALOG_REVALIDATE_SECONDS });
    const headers = new Headers(init.headers);
    expect(headers.get("cookie")).toBeNull();
    expect(headers.get("authorization")).toBeNull();
    expect(headers.get("x-csrf-token")).toBeNull();
    expect(headers.get("accept")).toBe("application/json");
  });

  it("fetches on-demand metadata without the catalog revalidate cache", async () => {
    stubEnv();
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      () =>
        Promise.resolve(
          new Response(JSON.stringify({ schema_version: 1, stars: 1, archived: false }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { publicApiGetLive } = await import("@/lib/api/public-http");
    await publicApiGetLive(
      "/v1/catalog/components/component_01JQZK7B8N4M6P2R9T5V0X3Y70/versions/1.0/github-metadata",
    );
    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.cache).toBe("no-store");
    expect(init).not.toHaveProperty("next");
  });

  it("rejects private endpoints and credential-bearing options", async () => {
    stubEnv();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => {
        throw new Error("fetch must not run");
      }),
    );
    const { publicApiGet } = await import("@/lib/api/public-http");
    await expect(publicApiGet("/v1/account")).rejects.toThrow(/non-allowlisted path/);
    await expect(publicApiGet("/v1/devices")).rejects.toThrow(/non-allowlisted path/);
    await expect(publicApiGet("/v1/owner/objects")).rejects.toThrow(/non-allowlisted path/);
    await expect(publicApiGet("/v1/grants")).rejects.toThrow(/non-allowlisted path/);
    await expect(publicApiGet("/v1/reports")).rejects.toThrow(/non-allowlisted path/);
    await expect(publicApiGet("/v1/staff/reports")).rejects.toThrow(/non-allowlisted path/);
    await expect(publicApiGet("/v1/account/public-profile")).rejects.toThrow(
      /non-allowlisted path/,
    );
    await expect(
      publicApiGet("/v1/catalog/services", {
        sessionToken: "session-fixture",
      } as never),
    ).rejects.toThrow(/sessionToken/);
    await expect(
      publicApiGet("/v1/catalog/services", {
        headers: { Cookie: "ai_stp_session=session-fixture" } as never,
      }),
    ).rejects.toThrow(/credential-bearing headers/);
  });

  it("does not turn a transport failure into an empty catalog", async () => {
    stubEnv();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("network down"))),
    );
    const { publicApiGet } = await import("@/lib/api/public-http");
    await expect(publicApiGet("/v1/catalog/components")).rejects.toMatchObject({
      name: "ApiError",
      code: "AI_STP_UNAVAILABLE",
    });
  });
});
