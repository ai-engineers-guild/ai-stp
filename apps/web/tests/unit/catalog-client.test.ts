import { afterEach, describe, expect, it, vi } from "vitest";

import { asComponentId, asCursorToken } from "@/lib/brands";

/**
 * Catalog client must forward the cursor literally and surface empty pages
 * without inventing items (SPEC-022 REQ-2206).
 */

vi.mock("next/headers", () => ({
  cookies: vi.fn(() => Promise.resolve({ get: () => undefined })),
}));

describe("catalog client searchComponents", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("forwards cursor and page_size and returns an empty page as data", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://api.test:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USE_MOCKS", "false");
    vi.stubEnv("AI_STP_MOCK_AUTH", "false");

    const emptyPage = {
      schema_version: 1,
      items: [],
      page: {
        schema_version: 1,
        next_cursor: null,
        page_size: 5,
      },
    };

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      expect(url).toContain("/v1/catalog/components");
      expect(url).toContain("cursor=cursor_fixture_token");
      expect(url).toContain("page_size=5");
      return Promise.resolve(
        new Response(JSON.stringify(emptyPage), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const { searchComponents } = await import("@/lib/api/catalog");
    const result = await searchComponents({
      cursor: asCursorToken("cursor_fixture_token"),
      page_size: 5,
    });
    expect(result.items).toEqual([]);
    expect(result.page.page_size).toBe(5);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("forwards repeated country and service filters", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://api.test:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USE_MOCKS", "false");
    vi.stubEnv("AI_STP_MOCK_AUTH", "false");

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      expect(url).toContain("country_codes=KZ");
      expect(url).toContain("country_codes=unspecified");
      expect(url).toContain("service_domains=kaspi.kz");
      expect(url).toContain("updated_from=2026-01-01");
      expect(url).toContain("updated_to=2026-01-31");
      return Promise.resolve(
        new Response(
          JSON.stringify({
            schema_version: 1,
            items: [],
            experimental: [],
            page: { schema_version: 1, next_cursor: null, page_size: 25 },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const { searchComponents } = await import("@/lib/api/catalog");
    await searchComponents({
      country_codes: ["KZ", "unspecified"],
      service_domains: ["kaspi.kz"],
      updated_from: "2026-01-01",
      updated_to: "2026-01-31",
    });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("maps a not-found detail into ApiError", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://api.test:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USE_MOCKS", "false");
    vi.stubEnv("AI_STP_MOCK_AUTH", "false");

    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              error: { code: "AI_STP_NOT_FOUND", message: "no such component" },
            }),
            { status: 404, headers: { "Content-Type": "application/json" } },
          ),
        ),
      ),
    );

    const { readComponent } = await import("@/lib/api/catalog");
    const { ApiError } = await import("@/lib/api/errors");
    await expect(
      readComponent(asComponentId("component_01JQZK7B8N4M6P2R9T5V0X3Y70")),
    ).rejects.toBeInstanceOf(ApiError);
  });
});
