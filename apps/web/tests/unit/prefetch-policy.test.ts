import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { isShellPrefetchHref, SHELL_PREFETCH_HREFS } from "@/lib/prefetch-policy";

function walk(dir: string): string[] {
  const entries = readdirSync(dir);
  const files: string[] = [];
  for (const entry of entries) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      files.push(...walk(full));
      continue;
    }
    if (full.endsWith(".ts") || full.endsWith(".tsx")) {
      files.push(full);
    }
  }
  return files;
}

describe("prefetch policy", () => {
  it("allowlists only the stable shell hrefs", () => {
    expect([...SHELL_PREFETCH_HREFS]).toEqual([
      "/",
      "/catalog",
      "/services",
      "/content",
      "/contact",
      "/login",
    ]);
    expect(isShellPrefetchHref("/catalog")).toBe(true);
    expect(isShellPrefetchHref("/catalog?q=rust")).toBe(false);
    expect(isShellPrefetchHref("/objects")).toBe(false);
    expect(isShellPrefetchHref("/account")).toBe(false);
    expect(isShellPrefetchHref("/staff/reports")).toBe(false);
  });

  it("does not force prefetch outside the shell allowlist", () => {
    const root = path.resolve(__dirname, "../../src");
    const allowedForced = new Set([
      path.normalize(path.join(root, "lib/prefetch-policy.ts")),
      path.normalize(path.join(root, "components/layouts/site-header.tsx")),
      path.normalize(path.join(root, "components/organisms/account-drawer.tsx")),
    ]);
    const forced: string[] = [];
    for (const file of walk(root)) {
      if (file.includes(`${path.sep}stories${path.sep}`)) continue;
      const source = readFileSync(file, "utf8");
      if (
        /(^|\s)prefetch(?!=)/.test(source) ||
        /prefetch=\{true\}/.test(source) ||
        /prefetch=\{isShellPrefetchHref/.test(source)
      ) {
        if (!allowedForced.has(path.normalize(file))) {
          forced.push(path.relative(root, file).replaceAll("\\", "/"));
        }
      }
    }
    expect(forced).toEqual([]);
  });

  it("disables prefetch on catalog pagination, object cards, and private lists", () => {
    const root = path.resolve(__dirname, "../../src");
    const required = [
      "components/organisms/catalog-page-nav.tsx",
      "components/organisms/object-card.tsx",
      "components/organisms/catalog-filters.tsx",
      "components/organisms/account-drawer.tsx",
      "components/molecules/catalog-choice-menu.tsx",
      "components/molecules/object-version-history.tsx",
      "app/[locale]/(site)/staff/reports/page.tsx",
      "app/[locale]/(site)/objects/[kind]/[stableId]/page.tsx",
    ];
    for (const rel of required) {
      const source = readFileSync(path.join(root, rel), "utf8");
      expect(source, rel).toContain("prefetch={false}");
    }
  });
});
