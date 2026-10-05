import { gzipSync } from "node:zlib";

import { expect, test } from "@playwright/test";

import { PERF_BUDGETS } from "../../src/lib/budgets";

/**
 * REQ-2213 measured gate: first-load client JS for the `/en` route (gzip).
 *
 * Measured from what the browser loads: every module script the served page
 * references, fetched from the running standalone server. A bundler manifest
 * is not a stable source — Next 16 no longer writes `app-build-manifest.json`,
 * and that manifest's page entry left out the layout chunks. `noModule`
 * scripts are legacy polyfills a module-capable browser never downloads.
 *
 * lcpMs / cls / tbtMs are recorded in PERF_BUDGETS but not measured here.
 */
test.describe("performance budgets (REQ-2213)", () => {
  test("landing route first-load JS gzip stays within budget", async ({ page, request }) => {
    const landing = await request.get("/en");
    expect(landing.ok(), `GET /en answered ${String(landing.status())}`).toBe(true);
    // The browser's own parser reads the served markup: no script runs, and
    // attribute case, quoting and entities are what the browser would see.
    const sources = new Set(
      await page.evaluate(
        (markup) => {
          const parsed = new DOMParser().parseFromString(markup, "text/html");
          return Array.from(parsed.querySelectorAll<HTMLScriptElement>("script[src]"))
            .filter((script) => !script.noModule)
            .map((script) => script.getAttribute("src") ?? "");
        },
        await landing.text(),
      ),
    );

    // A budget gate that cannot tell "within budget" from "measured nothing" is
    // not a gate: an unreadable chunk must fail here instead of passing as 0 KiB.
    expect(sources.size, "expected module scripts on the landing page").toBeGreaterThan(0);
    let totalGzipBytes = 0;
    for (const source of sources) {
      const script = await request.get(source);
      expect(script.ok(), `GET ${source} answered ${String(script.status())}`).toBe(true);
      totalGzipBytes += gzipSync(await script.body()).length;
    }

    const gzipKb = totalGzipBytes / 1024;
    expect(
      gzipKb,
      `landing JS gzip ${gzipKb.toFixed(1)} KiB over ${String(sources.size)} scripts exceeds budget ${String(PERF_BUDGETS.landingJsGzipKb)} KiB`,
    ).toBeLessThanOrEqual(PERF_BUDGETS.landingJsGzipKb);
  });
});
