import { describe, expect, it } from "vitest";

import {
  buildDevApiRewrites,
  resolveDevApiRewrites,
  shouldEnableDevApiRewrites,
} from "@/lib/dev-api-rewrites";

describe("dev API rewrites (same-origin hop without Caddy)", () => {
  it("enables rewrites only in development", () => {
    expect(shouldEnableDevApiRewrites("development")).toBe(true);
    expect(shouldEnableDevApiRewrites("production")).toBe(false);
    expect(shouldEnableDevApiRewrites("test")).toBe(false);
    expect(shouldEnableDevApiRewrites(undefined)).toBe(false);
  });

  it("maps /v1 and API docs paths to the internal API base", () => {
    const rules = buildDevApiRewrites("http://api:8000/");
    expect(rules).toEqual([
      { source: "/v1/:path*", destination: "http://api:8000/v1/:path*" },
      { source: "/docs", destination: "http://api:8000/docs" },
      { source: "/docs/:path*", destination: "http://api:8000/docs/:path*" },
      { source: "/redoc", destination: "http://api:8000/redoc" },
      { source: "/redoc/:path*", destination: "http://api:8000/redoc/:path*" },
      { source: "/openapi.json", destination: "http://api:8000/openapi.json" },
      {
        source: "/schemas/provider-protocol/:path*",
        destination: "http://api:8000/schemas/provider-protocol/:path*",
      },
    ]);
  });

  it("resolveDevApiRewrites is empty outside development", () => {
    expect(resolveDevApiRewrites("production", "http://api:8000")).toEqual([]);
  });

  it("resolveDevApiRewrites wires OAuth login path destination in development", () => {
    const rules = resolveDevApiRewrites("development", "http://api:8000");
    const v1 = rules.find((r) => r.source === "/v1/:path*");
    expect(v1?.destination).toBe("http://api:8000/v1/:path*");
    // Browser-relative OAuth hrefs such as /v1/auth/google/login match this rule.
    expect(v1?.source).toMatch(/^\/v1\//);
  });

  it("defaults API base when env is unset in development", () => {
    const rules = resolveDevApiRewrites("development", undefined);
    expect(rules.some((r) => r.destination.startsWith("http://localhost:8000/v1"))).toBe(true);
  });
});
