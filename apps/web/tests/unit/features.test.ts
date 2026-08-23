import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { FEATURE_KEYS } from "@/lib/features/definitions";
import { loadFeatureConfig, resolveFeatureProfile } from "@/lib/features/load-profile";

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

async function fixture(yaml: string): Promise<string> {
  const root = await mkdtemp(path.join(tmpdir(), "ai-stp-features-"));
  roots.push(root);
  mkdirSync(path.join(root, "config"));
  writeFileSync(path.join(root, "config", "features.yaml"), yaml, "utf8");
  return root;
}

const valid = `schema_version: 1\ndefault_profile: public_saas\nprofiles:\n  public_saas:\n    content_hub: true\n    saas_public_pages: true\n    catalog_usage_metrics: true\n  self_hosted:\n    content_hub: false\n    saas_public_pages: false\n    catalog_usage_metrics: false\n`;

describe("web feature profiles", () => {
  it("keeps the registry intentionally bounded to real consumers", () => {
    expect(FEATURE_KEYS).toEqual(["content_hub", "saas_public_pages", "catalog_usage_metrics"]);
    const consumers = [
      "src/middleware.ts",
      "src/lib/projection/navigation.ts",
      "src/lib/projection/registry.ts",
      "src/app/sitemap.ts",
      "src/app/robots.ts",
      "src/app/feed.xml/route.ts",
    ];
    for (const consumer of consumers) {
      expect(readFileSync(path.join(process.cwd(), consumer), "utf8")).toContain("content_hub");
    }
    for (const clientBoundary of [
      "src/components/layouts/site-header.tsx",
      "src/lib/projection/navigation.ts",
    ]) {
      const source = readFileSync(path.join(process.cwd(), clientBoundary), "utf8");
      expect(source).not.toMatch(/load-profile|js-yaml/);
    }
  });

  it("loads a complete profile and applies an explicit build override", async () => {
    const root = await fixture(valid);
    expect(resolveFeatureProfile(root, { AI_STP_WEB_PROFILE: "self_hosted" })).toEqual({
      profile: "self_hosted",
      features: { content_hub: false, saas_public_pages: false, catalog_usage_metrics: false },
    });
    expect(
      resolveFeatureProfile(root, {
        AI_STP_WEB_PROFILE: "self_hosted",
        AI_STP_FEATURE_CONTENT_HUB: "true",
      }).features.content_hub,
    ).toBe(true);
    expect(
      resolveFeatureProfile(root, {
        AI_STP_WEB_PROFILE: "public_saas",
        AI_STP_FEATURE_CONTENT_HUB: "",
        AI_STP_FEATURE_SAAS_PUBLIC_PAGES: "",
      }).features,
    ).toEqual({ content_hub: true, saas_public_pages: true, catalog_usage_metrics: true });
  });

  it.each([
    ["unknown key", valid.replace("content_hub: true", "other: true")],
    ["missing key", valid.replace("    content_hub: true\n", "")],
    ["non boolean", valid.replace("content_hub: true", "content_hub: yes")],
    ["unknown field", valid + "extra: true\n"],
    [
      "missing default profile",
      valid.replace("default_profile: public_saas", "default_profile: absent"),
    ],
  ])("rejects %s", async (_name, yaml) => {
    const root = await fixture(yaml);
    expect(() => loadFeatureConfig(root)).toThrow(/Invalid web feature config/);
  });

  it("rejects duplicate YAML keys", async () => {
    const root = await fixture(
      valid.replace("content_hub: true", "content_hub: true\n    content_hub: false"),
    );
    expect(() => loadFeatureConfig(root)).toThrow(/Invalid web feature YAML/);
  });

  it("rejects unknown profiles, overrides and override values", async () => {
    const root = await fixture(valid);
    expect(() => resolveFeatureProfile(root, { AI_STP_WEB_PROFILE: "absent" })).toThrow(
      /Unknown AI_STP_WEB_PROFILE/,
    );
    expect(() => resolveFeatureProfile(root, { AI_STP_FEATURE_UNKNOWN: "false" })).toThrow(
      /Unknown web feature override/,
    );
    expect(() => resolveFeatureProfile(root, { AI_STP_FEATURE_CONTENT_HUB: "1" })).toThrow(
      /exactly true or false/,
    );
  });
});
