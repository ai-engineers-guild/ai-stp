import { describe, expect, it } from "vitest";

import {
  isImpossibleCatalogObjectPath,
  isImpossibleCountryPath,
} from "@/lib/projection/missing-route";
import { isPagePath, pathWithoutLocale, projectedHref } from "@/lib/projection/paths";
import {
  parseProjectionRoute,
  projectionRequestHeaders,
  PROJECTION_HEADER,
  PROTECTED_SEGMENTS,
} from "@/lib/projection/route";

describe("projection route parsing (REQ-3602)", () => {
  it("detects machine routes and builds the canonical path", () => {
    const parsed = parseProjectionRoute("/en/ai/catalog");
    expect(parsed.isMachine).toBe(true);
    expect(parsed.projection).toBe("machine");
    expect(parsed.canonicalPathname).toBe("/en/catalog");
    expect(parsed.locale).toBe("en");
    expect(parsed.isProtected).toBe(false);
  });

  it("treats human routes as human even when x-projection is spoofed later", () => {
    const parsed = parseProjectionRoute("/en/catalog");
    expect(parsed.isMachine).toBe(false);
    expect(parsed.projection).toBe("human");
    expect(parsed.canonicalPathname).toBe("/en/catalog");
  });

  it("marks private segments from the canonical path", () => {
    const machinePrivate = parseProjectionRoute("/en/ai/account");
    expect(machinePrivate.isMachine).toBe(true);
    expect(machinePrivate.isProtected).toBe(true);
    expect(machinePrivate.canonicalPathname).toBe("/en/account");

    const humanPrivate = parseProjectionRoute("/ru/devices");
    expect(humanPrivate.isProtected).toBe(true);
    expect(humanPrivate.isMachine).toBe(false);
  });

  it("keeps locale handling for both machine locales", () => {
    for (const locale of ["en", "ru"] as const) {
      const parsed = parseProjectionRoute(`/${locale}/ai/catalog`);
      expect(parsed.isLocale).toBe(true);
      expect(parsed.locale).toBe(locale);
      expect(parsed.canonicalPathname).toBe(`/${locale}/catalog`);
    }
  });

  it("overwrites client-supplied x-projection headers", () => {
    const source = new Headers({ [PROJECTION_HEADER]: "machine" });
    const headers = projectionRequestHeaders(source, "human", "/en/catalog", "?q=1");
    expect(headers.get(PROJECTION_HEADER)).toBe("human");
    expect(headers.get("x-pathname")).toBe("/en/catalog");
    expect(headers.get("x-search")).toBe("?q=1");
  });

  it("keeps private routes behind the same session gate in both projections", () => {
    for (const pathname of ["/en/ai/account", "/en/account", "/ru/ai/devices"]) {
      const parsed = parseProjectionRoute(pathname);
      expect(parsed.isProtected, pathname).toBe(true);
      const pagePath = pathWithoutLocale(parsed.canonicalPathname, parsed.locale);
      expect(pagePath.startsWith("/ai")).toBe(false);
    }
  });

  it("never projects non-page targets such as API endpoints", () => {
    // /v1/... is served by the API, not by the localized page tree. Rewriting
    // it into the projection produced /en/ai/v1/auth/... and broke sign-in.
    expect(projectedHref("/v1/auth/google/login?client=web", "en")).toBe(
      "/v1/auth/google/login?client=web",
    );
    expect(projectedHref("/llms.txt", "en")).toBe("/llms.txt");
    expect(projectedHref("/agents.md", "ru")).toBe("/agents.md");
    expect(projectedHref("https://docs.example.test", "en")).toBe("https://docs.example.test");
    expect(isPagePath("/v1/auth/github/login")).toBe(false);
    expect(isPagePath("/en/catalog")).toBe(true);
  });

  it("keeps machine document links inside the machine projection", () => {
    expect(projectedHref("/login", "en")).toBe("/en/ai/login");
    expect(projectedHref("/en/contact", "en")).toBe("/en/ai/contact");
    expect(projectedHref("/account", "ru")).toBe("/ru/ai/account");
    expect(projectedHref("/catalog", "en")).toBe("/en/ai/catalog");
    expect(projectedHref("/", "ru")).toBe("/ru/ai");
  });

  it("treats impossible catalog ids and user-assigned country codes as missing", () => {
    expect(isImpossibleCatalogObjectPath("/en/catalog/components/component_missing")).toBe(true);
    expect(isImpossibleCatalogObjectPath("/en/ai/catalog/components/component_missing")).toBe(true);
    expect(
      isImpossibleCatalogObjectPath("/en/catalog/components/component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"),
    ).toBe(false);
    expect(isImpossibleCountryPath("/en/countries/ZZ")).toBe(true);
    expect(isImpossibleCountryPath("/en/ai/countries/ZZ")).toBe(true);
    expect(isImpossibleCountryPath("/en/countries/KZ")).toBe(false);
  });

  it("lists the private segments that machine routes must reject", () => {
    for (const segment of [
      "account",
      "devices",
      "objects",
      "access",
      "publications",
      "invitations",
      "reports",
      "staff",
    ]) {
      expect(PROTECTED_SEGMENTS.has(segment)).toBe(true);
    }
  });
});
