import { gzipSync } from "node:zlib";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { PERF_BUDGETS } from "../../src/lib/budgets";

/**
 * REQ-2213 measured gate: first-load client JS for the `/en` route (gzip).
 * Source: `.next/app-build-manifest.json` after `next build` / `next start`.
 *
 * lcpMs / cls / tbtMs are recorded in PERF_BUDGETS but not measured here.
 */
test.describe("performance budgets (REQ-2213)", () => {
  test("landing route first-load JS gzip stays within budget", () => {
    const distDir = process.env["AI_STP_NEXT_DIST_DIR"] ?? ".next";
    const manifestPath = path.resolve(process.cwd(), distDir, "app-build-manifest.json");
    expect(
      existsSync(manifestPath),
      `expected ${distDir}/app-build-manifest.json after next build`,
    ).toBe(true);

    const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as {
      pages: Record<string, string[]>;
    };

    // App Router keys vary by Next version; prefer locale landing, then root.
    const candidates = [
      "/[locale]/(site)/page",
      "/[locale]/page",
      "/[locale]",
      "/en/page",
      "/en",
      "/page",
      "/",
    ];
    let files: string[] | undefined;
    for (const key of candidates) {
      if (manifest.pages[key]?.length) {
        files = manifest.pages[key];
        break;
      }
    }
    // Fall back: union of all page entries that look like the locale landing.
    if (!files) {
      const landingKey = Object.keys(manifest.pages).find((key) =>
        /^\/\[locale\](?:\/\([^/]+\))?\/page$/.test(key),
      );
      files = landingKey ? manifest.pages[landingKey] : undefined;
    }
    // Last resort: sum unique files across the smallest page entry set that includes shared chunks.
    if (!files || files.length === 0) {
      const values = Object.values(manifest.pages);
      expect(values.length).toBeGreaterThan(0);
      files = [...new Set(values.flat())];
    }

    const staticDir = path.resolve(process.cwd(), distDir, "static");
    let totalGzipBytes = 0;
    let counted = 0;
    const unresolved: string[] = [];
    const seen = new Set<string>();
    for (const rel of files) {
      // Entries look like "static/chunks/...."
      const normalized = rel.replace(/^\//, "");
      if (seen.has(normalized) || !normalized.endsWith(".js")) {
        continue;
      }
      seen.add(normalized);
      const abs = path.resolve(process.cwd(), distDir, normalized);
      // Some manifests prefix with static/; also try under .next/static.
      const alt = path.resolve(staticDir, normalized.replace(/^static\//, ""));
      const found = existsSync(abs) ? abs : existsSync(alt) ? alt : null;
      if (!found) {
        unresolved.push(normalized);
        continue;
      }
      totalGzipBytes += gzipSync(readFileSync(found)).length;
      counted += 1;
    }

    // A budget gate that cannot tell "within budget" from "measured nothing" is
    // not a gate. An unreadable chunk or a manifest whose shape changed must
    // fail loudly here instead of passing as 0 KiB.
    expect(
      unresolved,
      `chunks listed in the manifest but not found on disk: ${unresolved.join(", ")}`,
    ).toEqual([]);
    expect(counted, "expected at least one JS chunk for the landing route").toBeGreaterThan(0);
    expect(totalGzipBytes, "measured 0 bytes — the measurement did not run").toBeGreaterThan(0);

    const gzipKb = totalGzipBytes / 1024;
    expect(
      gzipKb,
      `landing JS gzip ${gzipKb.toFixed(1)} KiB over ${String(counted)} chunks exceeds budget ${String(PERF_BUDGETS.landingJsGzipKb)} KiB`,
    ).toBeLessThanOrEqual(PERF_BUDGETS.landingJsGzipKb);
  });
});
