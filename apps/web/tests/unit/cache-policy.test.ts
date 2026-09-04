import { describe, expect, it } from "vitest";

import {
  assertNoCredentialHeaders,
  assertPublicGetPath,
  hasForbiddenPublicHeader,
  isPublicCatalogGetPath,
  PUBLIC_CATALOG_REVALIDATE_SECONDS,
} from "@/lib/api/cache-policy";

describe("public catalog cache policy", () => {
  it("exports one short revalidate TTL", () => {
    expect(PUBLIC_CATALOG_REVALIDATE_SECONDS).toBe(60);
    expect(Number.isInteger(PUBLIC_CATALOG_REVALIDATE_SECONDS)).toBe(true);
  });

  it("allowlists anonymous catalog and publisher GET paths", () => {
    expect(isPublicCatalogGetPath("/v1/catalog/services")).toBe(true);
    expect(isPublicCatalogGetPath("/v1/catalog/services/kaspi.kz")).toBe(true);
    expect(isPublicCatalogGetPath("/v1/catalog/countries/KZ")).toBe(true);
    expect(isPublicCatalogGetPath("/v1/catalog/components")).toBe(true);
    expect(
      isPublicCatalogGetPath("/v1/catalog/components/component_01JQZK7B8N4M6P2R9T5V0X3Y70"),
    ).toBe(true);
    expect(
      isPublicCatalogGetPath(
        "/v1/catalog/components/component_01JQZK7B8N4M6P2R9T5V0X3Y70/versions/1.0",
      ),
    ).toBe(true);
    expect(
      isPublicCatalogGetPath(
        "/v1/catalog/components/component_01JQZK7B8N4M6P2R9T5V0X3Y70/versions/1.0/github-metadata",
      ),
    ).toBe(true);
    expect(
      isPublicCatalogGetPath(
        "/v1/catalog/setups/setup_01JQZK7B8N4M6P2R9T5V0X3Y70/versions/1.0/context-budget",
      ),
    ).toBe(true);
    expect(isPublicCatalogGetPath("/v1/catalog/setups")).toBe(true);
    expect(isPublicCatalogGetPath("/v1/publishers/account_01JQZK7B8N4M6P2R9T5V0X3Y7Z")).toBe(true);
    expect(
      isPublicCatalogGetPath("/v1/seo/subjects/component/component_01JQZK7B8N4M6P2R9T5V0X3Y70"),
    ).toBe(true);
    expect(isPublicCatalogGetPath("/v1/seo/sitemap")).toBe(true);
    expect(isPublicCatalogGetPath("/v1/seo/sitemaps/component/en/1")).toBe(true);
    expect(isPublicCatalogGetPath("/v1/seo/catalog")).toBe(true);
    expect(
      isPublicCatalogGetPath(
        "/v1/seo/og/revision_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      ),
    ).toBe(true);
    expect(isPublicCatalogGetPath("/v1/content")).toBe(true);
    expect(isPublicCatalogGetPath("/v1/content/article/kind-skill")).toBe(true);
    expect(isPublicCatalogGetPath("/v1/content/blog_post/the-agent-is-the-consumer")).toBe(true);
    expect(isPublicCatalogGetPath("/v1/documents/personal-data-consent")).toBe(true);
    expect(isPublicCatalogGetPath("/v1/content/repository/state")).toBe(false);
    expect(isPublicCatalogGetPath("/v1/content/repository/import")).toBe(false);
    expect(isPublicCatalogGetPath("/v1/staff/content/article/staff-note")).toBe(false);
  });

  it("rejects account, private, and mutation-shaped paths", () => {
    const rejected = [
      "/v1/account",
      "/v1/account/public-profile",
      "/v1/auth/me",
      "/v1/devices",
      "/v1/owner/objects",
      "/v1/grants",
      "/v1/reports",
      "/v1/staff/reports",
      "/v1/catalog/components/extra/path",
    ];
    for (const path of rejected) {
      expect(isPublicCatalogGetPath(path)).toBe(false);
      expect(() => {
        assertPublicGetPath(path);
      }).toThrow(/non-allowlisted path/);
    }
  });

  it("detects credential headers without reading their values in messages", () => {
    expect(hasForbiddenPublicHeader({ Cookie: "x" })).toBe(true);
    expect(hasForbiddenPublicHeader({ Authorization: "Bearer x" })).toBe(true);
    expect(hasForbiddenPublicHeader({ "X-CSRF-Token": "x" })).toBe(true);
    expect(hasForbiddenPublicHeader({ Accept: "application/json" })).toBe(false);
    expect(() => {
      assertNoCredentialHeaders({ cookie: "x" });
    }).toThrow(/credential-bearing headers/);
  });
});
