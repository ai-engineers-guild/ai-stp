import type { SafetyCheckEntry, SafetyChecksSummary } from "@/lib/api/generated/types.gen";

const VERDICT = new Set(["passed", "failed", "warning"]);
const INCOMPLETE = new Set(["not_run", "degraded", "running"]);

export type CheckInfo = { name: string; description: string };

export const CHECK_INFO: Record<string, CheckInfo> = {
  structure: {
    name: "Passport structure",
    description: "Validates the passport schema and canonical form.",
  },
  digest: {
    name: "Artifact integrity",
    description: "Recomputes the digest so changed bytes cannot pass as the published version.",
  },
  license: { name: "License", description: "Checks that redistribution terms are declared." },
  tags: { name: "Catalog tags", description: "Validates required normalized catalog tags." },
  source_repo: {
    name: "Source provenance",
    description: "Confirms the exact public repository, commit and path.",
  },
  artifact_unpack: {
    name: "Safe unpacking",
    description: "Unpacks the artifact within size and file-count limits.",
  },
  path_denylist: {
    name: "Dangerous paths",
    description: "Rejects secrets, credentials, device files and unsafe paths.",
  },
  secrets_heuristic: {
    name: "Secret patterns",
    description: "Looks for likely tokens, private keys and credentials.",
  },
  secrets_gitleaks: {
    name: "Gitleaks secret scan",
    description: "Runs the Gitleaks ruleset over the artifact.",
  },
  content_hidden: {
    name: "Hidden content",
    description: "Detects concealed instructions and suspicious invisible content.",
  },
  pi_content_pack: {
    name: "Prompt injection",
    description: "Looks for instructions that attempt to override the agent or exfiltrate data.",
  },
  network_intent: {
    name: "Network intent",
    description: "Finds downloads piped to a shell and dangerous URL schemes, without DNS lookups.",
  },
  agentic_behavior: {
    name: "Agentic behavior",
    description: "Flags mechanically provable dangerous agent or skill declarations.",
  },
  sast_opengrep: {
    name: "Static code analysis",
    description: "Uses owned Opengrep rules to find unsafe code patterns.",
  },
  mcp_config_static: {
    name: "MCP configuration",
    description: "Validates MCP server maps, transports and dangerous capability chains.",
  },
  hook_schema_static: {
    name: "Hook schema",
    description: "Checks hook event, matcher and execution schema.",
  },
  hook_command_argv: {
    name: "Hook commands",
    description: "Requires hook execution as an argument array without unsafe substitution.",
  },
  skill_static_gate: {
    name: "Agent skill policy",
    description: "Checks skill metadata, permissions and malicious instruction patterns.",
  },
  shell_obfuscation: {
    name: "Shell obfuscation",
    description: "Detects encoded or concatenated payloads that decode to a shell command.",
  },
  sast_shellcheck: {
    name: "ShellCheck",
    description: "Runs ShellCheck on shell scripts in the artifact.",
  },
  sast_bandit: {
    name: "Bandit",
    description: "Runs Bandit on Python sources outside test trees.",
  },
  sca_pip_audit: {
    name: "pip-audit",
    description: "Audits pinned Python requirements offline when a lock file exists.",
  },
  sast_gosec: { name: "gosec", description: "Runs gosec on Go sources." },
  sca_govulncheck: {
    name: "govulncheck",
    description: "Checks Go modules for known vulnerabilities.",
  },
  sca_cargo_audit: {
    name: "cargo-audit",
    description: "Checks Rust crates for known vulnerabilities.",
  },
  sca_cargo_deny: {
    name: "cargo-deny",
    description: "Applies cargo-deny policy to Rust dependencies.",
  },
  sast_eslint_security: {
    name: "ESLint security",
    description: "Runs eslint-plugin-security on JavaScript and TypeScript.",
  },
  sca_npm_audit: {
    name: "npm audit",
    description: "Runs npm audit when a JavaScript manifest exists.",
  },
  document_pdf: {
    name: "PDF document",
    description: "Inspects PDF JavaScript, OpenAction and prompt-injection strings.",
  },
  sca_osv: {
    name: "OSV Scanner",
    description: "Looks up known vulnerabilities in an offline OSV database.",
  },
  malware_clamav: { name: "ClamAV", description: "Scans binary content with ClamAV signatures." },
  malware_yara: { name: "YARA", description: "Matches owned YARA rules against the artifact." },
  setup_pin_aggregate: {
    name: "Setup pins",
    description: "Joins exact component pins and their published check summaries.",
  },
};

export const CHECK_IDS = Object.keys(CHECK_INFO);

export function humanizeCheckId(checkId: string): string {
  return checkId.replaceAll("_", " ");
}

export function checkInfoFor(checkId: string, localized?: Record<string, CheckInfo>): CheckInfo {
  return (
    localized?.[checkId] ??
    CHECK_INFO[checkId] ?? { name: humanizeCheckId(checkId), description: "" }
  );
}

export function isUserFacingCheck(check: SafetyCheckEntry): boolean {
  if (VERDICT.has(check.result)) return true;
  return INCOMPLETE.has(check.result) && check.mandatory;
}

export function verdictPercent(checks: readonly SafetyCheckEntry[]): number | null {
  const verdicts = checks.filter((check) => VERDICT.has(check.result));
  if (!verdicts.length) return null;
  return Math.round(
    (100 * verdicts.filter((check) => check.result === "passed").length) / verdicts.length,
  );
}

export function gatePercent(checks: readonly SafetyCheckEntry[]): number | null {
  return verdictPercent(checks.filter((check) => check.mandatory));
}

export function extraPercent(checks: readonly SafetyCheckEntry[]): number | null {
  return verdictPercent(checks.filter((check) => !check.mandatory));
}

export function mandatoryFailed(checks: readonly SafetyCheckEntry[]): boolean {
  return checks.some((check) => check.mandatory && check.result === "failed");
}

export function policyPercent(summary: SafetyChecksSummary): number | null {
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
