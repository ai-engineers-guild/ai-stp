import { afterEach, expect, it, vi } from "vitest";

// Shared corporate URLs take the explicit rewrite branch, before intl routing.
vi.mock("next-intl/middleware", () => ({
  default: () => () => new Response(null, { status: 200 }),
}));

afterEach(() => {
  vi.resetModules();
  vi.unstubAllEnvs();
});

it("prefixes shared corporate links once and preserves query strings", async () => {
  vi.stubEnv("AI_STP_COMPILED_FEATURE_PROFILE", "corporate_hub");
  const { corporateHref, corporateSharedPath } = await import("@/lib/features/corporate-path");
  const { projectedHref } = await import("@/lib/projection/paths");
  for (const href of ["/catalog?q=skill", "/account/profile", "/likes", "/login?returnTo=x"]) {
    expect(corporateHref(href)).toBe(`/corporate${href}`);
    expect(corporateHref(corporateHref(href))).toBe(`/corporate${href}`);
  }
  expect(corporateHref("/en/account")).toBe("/en/corporate/account");
  expect(corporateHref("/en/ai/account?tab=profile")).toBe("/en/ai/corporate/account?tab=profile");
  expect(corporateHref("/ru/corporate/account")).toBe("/ru/corporate/account");
  expect(corporateHref("/")).toBe("/corporate/overview");
  expect(corporateHref("https://docs.test")).toBe("https://docs.test");
  expect(projectedHref(corporateHref("/account"), "en")).toBe("/en/ai/corporate/account");
  expect(projectedHref(corporateHref("/corporate/overview"), "en")).toBe(
    "/en/ai/corporate/overview",
  );
  expect(corporateSharedPath("/ru/ai/corporate/account/profile")).toBe("/ru/ai/account/profile");
  expect(corporateSharedPath("/en/corporate/catalog")).toBe("/en/catalog");
  expect(corporateSharedPath("/en/corporate/organization/admins")).toBeNull();
  expect(corporateSharedPath("/en/corporate/technology-landscape")).toBeNull();
});

it("preserves personal and packaged website URLs", async () => {
  vi.stubEnv("AI_STP_COMPILED_FEATURE_PROFILE", "public_saas");
  const { corporateHref } = await import("@/lib/features/corporate-path");
  expect(corporateHref("/account")).toBe("/account");
  expect(corporateHref("/")).toBe("/");
});

it("rewrites corporate shared pages and retains private session gates", async () => {
  vi.stubEnv("AI_STP_COMPILED_FEATURE_PROFILE", "corporate_hub");
  const { NextRequest } = await import("next/server");
  const { default: middleware } = await import("@/middleware");
  const request = (page: string) => new NextRequest(`http://localhost${page}`);
  const legacy = middleware(request("/en/catalog?q=skill"));
  expect(legacy.headers.get("location")).toBe("http://localhost/en/corporate/catalog?q=skill");
  const catalog = middleware(request("/en/corporate/catalog?q=skill"));
  expect(catalog.headers.get("x-middleware-rewrite")).toBe("http://localhost/en/catalog?q=skill");
  expect(catalog.headers.get("x-middleware-request-x-pathname")).toBe("/en/catalog");
  const privatePage = middleware(request("/ru/ai/corporate/account/profile?tab=links"));
  const login = new URL(privatePage.headers.get("location") ?? "");
  expect(login.pathname).toBe("/ru/ai/corporate/login");
  expect(login.searchParams.get("returnTo")).toBe("/ru/ai/corporate/account/profile?tab=links");
  const signedIn = request("/en/corporate/account");
  const { SESSION_COOKIE } = await import("@/lib/auth/cookies");
  signedIn.cookies.set(SESSION_COOKIE, "presence-only");
  expect(middleware(signedIn).headers.get("x-middleware-rewrite")).toBe(
    "http://localhost/en/account",
  );
  expect(middleware(request("/en/corporate/catalog/components/component_missing")).status).toBe(
    404,
  );

  const loopbackRequest = new NextRequest("http://localhost:6767/en/corporate/login", {
    headers: { host: "127.0.0.1:6767" },
  });
  const rewrite = middleware(loopbackRequest);
  expect(rewrite.headers.get("x-middleware-rewrite")).toBe("http://127.0.0.1:6767/en/login");
  expect(rewrite.headers.get("location")).toBeNull();

  const mismatchedPort = new NextRequest("http://localhost:6767/en/corporate/login", {
    headers: { host: "127.0.0.1:6768" },
  });
  expect(middleware(mismatchedPort).headers.get("x-middleware-rewrite")).toBe(
    "http://localhost:6767/en/login",
  );

  const userinfoHost = new NextRequest("http://localhost:6767/en/corporate/login", {
    headers: { host: "user@127.0.0.1:6767" },
  });
  expect(middleware(userinfoHost).headers.get("x-middleware-rewrite")).toBe(
    "http://localhost:6767/en/login",
  );
});

it("keeps SaaS page URLs physical without corporate aliases", async () => {
  vi.stubEnv("AI_STP_COMPILED_FEATURE_PROFILE", "public_saas");
  const { NextRequest } = await import("next/server");
  const { default: middleware } = await import("@/middleware");
  const response = middleware(new NextRequest("http://localhost/en/catalog?q=skill"));
  expect(response.headers.get("location")).toBeNull();
  expect(response.headers.get("x-middleware-rewrite")).toBeNull();
});
