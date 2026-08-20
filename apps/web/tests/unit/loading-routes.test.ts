import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const here = path.dirname(fileURLToPath(import.meta.url));
const localeApp = path.resolve(here, "../../src/app/[locale]");

function listLoadingFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) {
      out.push(...listLoadingFiles(full));
      continue;
    }
    if (name === "loading.tsx") {
      out.push(full);
    }
  }
  return out;
}

describe("route loading UI", () => {
  it("ships locale and data-bound segment loading.tsx shells", () => {
    const files = listLoadingFiles(localeApp);
    const rel = files.map((f) => path.relative(localeApp, f).replaceAll("\\", "/"));
    expect(rel).toEqual(
      expect.arrayContaining([
        // Catalog list keeps a shell; object/country pages must not sit under
        // a parent loading.tsx or Next.js streams notFound() as HTTP 200.
        "(site)/catalog/(index)/loading.tsx",
        "(site)/account/loading.tsx",
        "(site)/devices/loading.tsx",
        "(site)/login/loading.tsx",
      ]),
    );
    expect(rel).not.toContain("(site)/loading.tsx");
    expect(rel).not.toContain("(site)/catalog/loading.tsx");
    for (const file of files) {
      const src = readFileSync(file, "utf8");
      expect(src).toMatch(/RouteLoading|Skeleton/);
      expect(src).toMatch(/loading/);
    }
  });
});
