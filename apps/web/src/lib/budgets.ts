/**
 * Recorded performance / accessibility budgets (design #82 resolved decision 2).
 *
 * Measured gates:
 * - `landingJsGzipKb` — enforced by `tests/e2e/perf-budget.spec.ts` against the
 *   module scripts the served `/en` page loads. 240 since Next 16 (2026-10-05):
 *   that measure read 207 KiB on Next 15 and 229 KiB on Next 16, where the
 *   framework runtime is most of it; the former 200 was checked against the
 *   page entry alone, without the layout chunks.
 * - axe critical/serious — enforced by `tests/e2e/a11y.spec.ts`
 *
 * Not measured yet (recorded only, not a self-passing unit gate):
 * - `lcpMs`, `cls`, `tbtMs` — need a real browser performance observer harness
 */
export const PERF_BUDGETS = {
  lcpMs: 2500,
  cls: 0.1,
  tbtMs: 200,
  landingJsGzipKb: 240,
} as const;

export const A11Y_BUDGETS = {
  axeCritical: 0,
  axeSerious: 0,
  wcag: "2.1 AA",
} as const;
