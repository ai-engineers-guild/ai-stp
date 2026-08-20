import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { A11Y_BUDGETS, PERF_BUDGETS } from "@/lib/budgets";

/**
 * Confirms the module is the single recorded source. Measured enforcement lives
 * in e2e (`perf-budget.spec.ts`, `a11y.spec.ts`); lcp/cls/tbt are not measured yet.
 */
describe("perf/a11y budgets source (REQ-2213)", () => {
  it("exports positive measured thresholds and zero axe critical/serious", () => {
    expect(PERF_BUDGETS.landingJsGzipKb).toBeGreaterThan(0);
    expect(A11Y_BUDGETS.axeCritical).toBe(0);
    expect(A11Y_BUDGETS.axeSerious).toBe(0);
    expect(A11Y_BUDGETS.wcag).toMatch(/AA/);
  });

  it("is imported by the measured e2e gates rather than duplicated", () => {
    const root = path.resolve(__dirname, "..");
    const perf = readFileSync(path.join(root, "e2e/perf-budget.spec.ts"), "utf8");
    const a11y = readFileSync(path.join(root, "e2e/a11y.spec.ts"), "utf8");
    expect(perf).toMatch(/@\/lib\/budgets|lib\/budgets/);
    expect(a11y).toMatch(/@\/lib\/budgets|lib\/budgets/);
    expect(perf).toContain("PERF_BUDGETS");
    expect(a11y).toContain("A11Y_BUDGETS");
  });
});
