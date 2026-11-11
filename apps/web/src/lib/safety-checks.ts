import type { SafetyCheckEntry, SafetyChecksSummary } from "@/lib/api/generated/types.gen";

const VERDICT = new Set(["passed", "failed", "warning"]);

function verdictPercent(checks: readonly SafetyCheckEntry[]): number | null {
  const verdicts = checks.filter((check) => VERDICT.has(check.result));
  if (!verdicts.length) return null;
  return Math.round(
    (100 * verdicts.filter((check) => check.result === "passed").length) / verdicts.length,
  );
}

function gatePercent(checks: readonly SafetyCheckEntry[]): number | null {
  return verdictPercent(checks.filter((check) => check.mandatory));
}

export function mandatoryFailed(checks: readonly SafetyCheckEntry[]): boolean {
  return checks.some((check) => check.mandatory && check.result === "failed");
}

function policyPercent(summary: SafetyChecksSummary): number | null {
  const denom = summary.passed + summary.failed + summary.warning;
  if (denom > 0) return Math.round((100 * summary.passed) / denom);
  if (typeof summary.checks_passed_percent === "number") return summary.checks_passed_percent;
  return verdictPercent(summary.checks);
}

export function publicationScore(summary: SafetyChecksSummary): number | null {
  const fromChecks = gatePercent(summary.checks);
  if (fromChecks !== null) return fromChecks;
  return policyPercent(summary);
}
