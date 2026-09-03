import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a {...props}>{children ?? "Link"}</a>
  ),
}));

import { SafetyChecksSummaryView } from "@/components/molecules/safety-checks-summary";
import type { SafetyChecksSummary } from "@/lib/api/generated/types.gen";

const labels = {
  title: "Safety checks",
  status: "Scan status",
  percent: "Passed",
  passed: "Passed checks",
  failed: "Failed checks",
  warning: "Warnings",
  notRun: "Not run",
  incomplete: "Optional scanners missing",
  empty: "No checks recorded",
  noScan: "Not scanned yet",
  available: "Complete",
  pending: "Pending required checks",
  mandatory: "Required",
  resultPassed: "Passed result",
  resultFailed: "Failed result",
  resultWarning: "Warning result",
  resultNotRun: "Not-run result",
  resultDegraded: "Degraded result",
  gate: "Publication gate",
  extra: "Extra scanners",
  summary: "Automated checks reduce known risks.",
  checksComplete: "checks passed",
  expand: "Review individual checks",
  documentation: "How checks work",
  why: "Why",
  help: "About safety checks",
  findings: "Findings",
  rules: "Types",
  paths: "Files",
  payloadHidden: "Finding content is hidden.",
};

function summary(overrides: Partial<SafetyChecksSummary> = {}): SafetyChecksSummary {
  return {
    schema_version: 1,
    status: "available",
    checks_passed_percent: 100,
    coverage_complete: true,
    passed: 1,
    failed: 0,
    warning: 0,
    not_run: 0,
    total_countable: 1,
    components: [],
    checks: [
      {
        schema_version: 1,
        check_id: "path_denylist",
        result: "passed",
        mandatory: true,
        source: "platform_safety_scan",
        family: "path",
        reason: null,
        finding_summary: null,
      },
    ],
    ...overrides,
  };
}

describe("SafetyChecksSummaryView", () => {
  it("renders a compact summary with accessible progress and documentation", async () => {
    const user = userEvent.setup();
    render(<SafetyChecksSummaryView summary={summary()} labels={labels} />);

    expect(screen.getByRole("link", { name: "How checks work" })).toHaveAttribute(
      "href",
      "/docs/security-checks",
    );
    expect(screen.getByRole("link", { name: "About safety checks" })).toHaveAttribute(
      "href",
      "/docs/security-checks",
    );
    expect(screen.getByRole("button", { name: /Safety checks/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    await user.click(screen.getByRole("button", { name: /Safety checks/ }));
    expect(screen.getByText("Complete")).toBeInTheDocument();
    expect(screen.getAllByText("100%").length).toBeGreaterThan(0);
    expect(screen.getByText("1 / 1 checks passed")).toBeInTheDocument();
  });

  it("shows individual checks after expanding the single accordion", async () => {
    const user = userEvent.setup();
    render(<SafetyChecksSummaryView summary={summary()} labels={labels} />);

    await user.click(screen.getByRole("button", { name: /Safety checks/ }));

    expect(screen.getByText("path_denylist")).toBeInTheDocument();
    expect(screen.getByText("Passed result")).toBeInTheDocument();
    expect(screen.getByText("Required")).toBeInTheDocument();
  });

  it("shows a reason for an unsuccessful check", async () => {
    const user = userEvent.setup();
    render(
      <SafetyChecksSummaryView
        summary={summary({
          status: "available",
          checks_passed_percent: 0,
          passed: 0,
          failed: 1,
          checks: [
            {
              schema_version: 1,
              check_id: "path_denylist",
              result: "failed",
              mandatory: true,
              source: "platform_safety_scan",
              family: "path",
              reason: "unsafe path detected",
              finding_summary: null,
            },
          ],
        })}
        labels={labels}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Safety checks/ }));
    expect(screen.getAllByText(/unsafe path detected/).length).toBeGreaterThan(0);
  });

  it("renders warning reasons, not only a count", async () => {
    const user = userEvent.setup();
    render(
      <SafetyChecksSummaryView
        summary={summary({
          passed: 0,
          warning: 1,
          checks_passed_percent: 0,
          checks: [
            {
              schema_version: 1,
              check_id: "secrets_heuristic",
              result: "warning",
              mandatory: true,
              source: "platform_safety_scan",
              family: "secrets",
              reason: "possible token-like string",
              finding_summary: null,
            },
          ],
        })}
        labels={labels}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Safety checks/ }));
    expect(screen.getAllByText(/possible token-like string/).length).toBeGreaterThan(0);
  });

  it("shows bounded finding identifiers without rendering payload", async () => {
    const user = userEvent.setup();
    render(
      <SafetyChecksSummaryView
        summary={summary({
          passed: 0,
          warning: 1,
          checks_passed_percent: 0,
          checks: [
            {
              schema_version: 1,
              check_id: "skill_static_gate",
              result: "warning",
              mandatory: true,
              source: "platform_safety_scan",
              family: "agentic",
              reason: "findings_detected",
              finding_summary: {
                schema_version: 1,
                count: 2,
                severity_max: "high",
                rule_ids: ["capability_laundering", "remote_instruction_loading"],
                paths: ["SKILL.md"],
                truncated: false,
              },
            },
          ],
        })}
        labels={labels}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Safety checks/ }));
    expect(screen.getByText(/capability_laundering, remote_instruction_loading/)).toBeVisible();
    expect(screen.getByText(/SKILL.md/)).toBeVisible();
    expect(screen.getByText("Finding content is hidden.")).toBeVisible();
  });

  it("shows the percent when coverage is incomplete", async () => {
    const user = userEvent.setup();
    render(
      <SafetyChecksSummaryView
        summary={summary({
          status: "incomplete",
          checks_passed_percent: 71,
          coverage_complete: false,
          passed: 15,
          failed: 2,
          warning: 4,
          not_run: 0,
          total_countable: 21,
          checks: [
            {
              schema_version: 1,
              check_id: "path_denylist",
              result: "passed",
              mandatory: true,
              source: "platform_safety_scan",
              family: "path",
              reason: null,
              finding_summary: null,
            },
            {
              schema_version: 1,
              check_id: "network_intent",
              result: "failed",
              mandatory: false,
              source: "platform_safety_scan",
              family: "network_intent",
              reason: "url_pipe_shell",
              finding_summary: null,
            },
            {
              schema_version: 1,
              check_id: "sast_bandit",
              result: "warning",
              mandatory: false,
              source: "platform_safety_scan",
              family: "sast_python",
              reason: "b603",
              finding_summary: null,
            },
          ],
        })}
        labels={labels}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Safety checks/ }));
    expect(screen.getByText("Optional scanners missing")).toBeInTheDocument();
    expect(screen.getByText("71%")).toBeInTheDocument();
    expect(screen.getByText("15 / 21 checks passed")).toBeInTheDocument();
    expect(screen.getByText(/Publication gate/)).toBeInTheDocument();
    expect(screen.getByText(/Extra scanners/)).toBeInTheDocument();
    expect(screen.getByText("Network intent")).toBeInTheDocument();
    expect(screen.getByText("Failed result")).toBeInTheDocument();
    expect(screen.getByText("Warning result")).toBeInTheDocument();
    const failed = screen.getByText("Failed result");
    expect(failed.closest("[data-ui]")).toHaveClass("bg-destructive");
  });

  it("hides optional unfinished checks and recomputes a stale stored percent", async () => {
    const user = userEvent.setup();
    render(
      <SafetyChecksSummaryView
        summary={summary({
          status: "incomplete",
          checks_passed_percent: 60,
          coverage_complete: false,
          passed: 15,
          failed: 2,
          warning: 4,
          not_run: 4,
          total_countable: 25,
          checks: [
            {
              schema_version: 1,
              check_id: "path_denylist",
              result: "passed",
              mandatory: true,
              source: "platform_safety_scan",
              family: "path",
              reason: null,
              finding_summary: null,
            },
            {
              schema_version: 1,
              check_id: "sca_osv",
              result: "not_run",
              mandatory: false,
              source: "platform_safety_scan",
              family: "sca",
              reason: "offline_db_missing",
              finding_summary: null,
            },
            {
              schema_version: 1,
              check_id: "sca_pip_audit",
              result: "degraded",
              mandatory: false,
              source: "platform_safety_scan",
              family: "sca_python",
              reason: "timeout",
              finding_summary: null,
            },
          ],
        })}
        labels={labels}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Safety checks/ }));
    expect(screen.getByText("71%")).toBeInTheDocument();
    expect(screen.getByText("15 / 21 checks passed")).toBeInTheDocument();
    expect(screen.queryByText("OSV Scanner")).not.toBeInTheDocument();
    expect(screen.queryByText("pip-audit")).not.toBeInTheDocument();
    expect(screen.queryByText("Degraded result")).not.toBeInTheDocument();
    expect(screen.getByText("Dangerous paths")).toBeInTheDocument();
    expect(screen.getByText("path_denylist")).toBeInTheDocument();
  });

  it("names a degraded result instead of calling it not run", async () => {
    const user = userEvent.setup();
    render(
      <SafetyChecksSummaryView
        summary={summary({
          passed: 0,
          not_run: 0,
          checks: [
            {
              schema_version: 1,
              check_id: "sca_pip_audit",
              result: "degraded",
              mandatory: true,
              source: "platform_safety_scan",
              family: "sca_python",
              reason: "timeout",
              finding_summary: null,
            },
          ],
        })}
        labels={labels}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Safety checks/ }));
    expect(screen.getByText("Degraded result")).toBeInTheDocument();
    expect(screen.queryByText("Not-run result")).not.toBeInTheDocument();
  });

  it("uses localized pending and empty labels in compact mode", () => {
    const { rerender } = render(
      <SafetyChecksSummaryView
        summary={summary({ status: "pending", checks_passed_percent: null })}
        labels={labels}
        compact
      />,
    );
    expect(screen.getByText("Pending required checks")).toBeInTheDocument();

    rerender(
      <SafetyChecksSummaryView
        summary={summary({ status: "empty", checks_passed_percent: null, checks: [] })}
        labels={labels}
        compact
      />,
    );
    expect(screen.getByText("No checks recorded")).toBeInTheDocument();
  });

  it("distinguishes an absent scan from an empty scan", () => {
    render(<SafetyChecksSummaryView summary={null} labels={labels} />);

    expect(screen.getByRole("button", { name: /Safety checks/ })).toBeInTheDocument();
    expect(screen.getByText("Not scanned yet")).toBeInTheDocument();
  });
});
