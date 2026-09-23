import { existsSync } from "node:fs";
import path from "node:path";

import { createValidFileMatcher } from "next/dist/server/lib/find-page-file";
import { describe, expect, it, vi } from "vitest";

import {
  disabledWebModuleAliases,
  resolveFeatureProfile,
  webPageExtensions,
} from "@/lib/features/load-profile";

const publicPages = [
  "services/page.regional.tsx",
  "services/[domain]/page.regional.tsx",
  "countries/[code]/page.regional.tsx",
  "contact/page.saas.tsx",
  "legal/[slug]/page.saas.tsx",
  "(content)/content/page.content.tsx",
  "(content)/content/[type]/[slug]/page.content.tsx",
];

describe("native build route isolation (REQ-8309)", () => {
  it("serves unmatched routes without requiring the locale root layout", async () => {
    vi.resetModules();
    const { default: config } = await import("../../next.config");
    expect(config.experimental?.globalNotFound).toBe(true);
    expect(existsSync(path.join(process.cwd(), "src/app/global-not-found.tsx"))).toBe(true);
    expect(existsSync(path.join(process.cwd(), "src/app/not-found.tsx"))).toBe(false);
  });

  it.each(["public_saas", "self_hosted", "corporate_hub"])(
    "only disables middleware URL normalization in %s",
    async (profile) => {
      vi.resetModules();
      vi.stubEnv("AI_STP_WEB_PROFILE", profile);
      const { default: config } = await import("../../next.config");
      expect(config.skipMiddlewareUrlNormalize).toBe(profile === "corporate_hub");
      vi.unstubAllEnvs();
    },
  );

  it.each([
    ["public_saas", []],
    ["self_hosted", ["@/lib/api/content$", "@/lib/content/presenter$", "@/lib/api/public-legal$"]],
    [
      "corporate_hub",
      [
        "@/lib/api/content$",
        "@/lib/content/presenter$",
        "@/lib/api/public-legal$",
        "@/lib/projection/regional-presenters$",
      ],
    ],
  ])("aliases only disabled server modules in %s", (profile, expected) => {
    const config = resolveFeatureProfile(process.cwd(), { AI_STP_WEB_PROFILE: profile });
    expect(Object.keys(disabledWebModuleAliases(config, "/disabled-public-surface.ts"))).toEqual(
      expected,
    );
  });

  it("filters disabled machine routes before resolver dispatch", async () => {
    vi.resetModules();
    vi.stubEnv("AI_STP_COMPILED_FEATURE_PROFILE", "corporate_hub");
    vi.stubEnv("AI_STP_COMPILED_FEATURE_CONTENT_HUB", "false");
    vi.stubEnv("AI_STP_COMPILED_FEATURE_SAAS_PUBLIC_PAGES", "false");
    const corporate = await import("@/lib/projection/registry");
    expect(corporate.MACHINE_DISPATCH_PATTERNS).not.toEqual(
      expect.arrayContaining(["content", "legal/:slug", "services", "countries/:code"]),
    );

    vi.resetModules();
    vi.stubEnv("AI_STP_COMPILED_FEATURE_PROFILE", "public_saas");
    vi.stubEnv("AI_STP_COMPILED_FEATURE_CONTENT_HUB", "true");
    vi.stubEnv("AI_STP_COMPILED_FEATURE_SAAS_PUBLIC_PAGES", "true");
    const saas = await import("@/lib/projection/registry");
    expect(saas.MACHINE_DISPATCH_PATTERNS).toEqual(
      expect.arrayContaining(["content", "legal/:slug", "services", "countries/:code"]),
    );
    vi.unstubAllEnvs();
  });

  it.each(["CONTENT_HUB", "SAAS_PUBLIC_PAGES"])(
    "rejects personal surface override %s in corporate builds",
    (feature) => {
      expect(() =>
        resolveFeatureProfile(process.cwd(), {
          AI_STP_WEB_PROFILE: "corporate_hub",
          [`AI_STP_FEATURE_${feature}`]: "true",
        }),
      ).toThrow("Corporate builds cannot enable");
    },
  );
  it.each(["public_saas", "corporate_hub", "self_hosted"])(
    "discovers only enabled route modules in %s",
    (profile) => {
      const config = resolveFeatureProfile(process.cwd(), { AI_STP_WEB_PROFILE: profile });
      const matcher = createValidFileMatcher(webPageExtensions(config), undefined);
      for (const file of publicPages) {
        expect(matcher.isAppRouterPage(file), file).toBe(
          file.endsWith("regional.tsx") ? profile !== "corporate_hub" : profile === "public_saas",
        );
      }
      expect(matcher.isAppRouterRoute("feed.xml/route.content.ts")).toBe(profile === "public_saas");
      expect(matcher.isAppLayoutPage("(content)/layout.content.tsx")).toBe(
        profile === "public_saas",
      );
      expect(matcher.isAppRouterPage("corporate/overview/page.tsx")).toBe(true);
      expect(matcher.isAppRouterPage("catalog/page.tsx")).toBe(true);
    },
  );

  it("selects independent content and SaaS extensions for explicit overrides", () => {
    const config = resolveFeatureProfile(process.cwd(), {
      AI_STP_WEB_PROFILE: "public_saas",
      AI_STP_FEATURE_CONTENT_HUB: "false",
    });
    const matcher = createValidFileMatcher(webPageExtensions(config), undefined);
    expect(matcher.isAppRouterPage("content/page.content.tsx")).toBe(false);
    expect(matcher.isAppRouterPage("contact/page.saas.tsx")).toBe(true);
  });
});
