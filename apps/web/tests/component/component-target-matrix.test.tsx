import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { ComponentTargetMatrix } from "@/components/molecules/component-target-matrix";
import type { TargetMatrix } from "@/lib/api/generated/types.gen";

const labels = {
  heading: "Harness targets",
  summary: "Exact projections and author portability claims.",
  score: "Exact targets verified",
  harness: "Harness",
  availability: "Availability",
  exact: "Exact projection",
  claimedPortable: "Claimed portable",
  scope: "Scope",
  implementation: "Implementation",
  projectionKind: "Projection",
  technicalSupport: "Technical support",
  supportSupported: "Supported",
  supportExperimental: "Experimental",
  supportUnsupported: "Unsupported",
  assessment: "Assessment",
  safetyCheck: "Safety check",
  projectionDetails: "Open projection details",
  notVerified: "Not verified",
  verified: "Verified",
  failed: "Failed",
  stale: "Stale",
  recommendation: "Recommendation",
  recommended: "Recommended",
  notRecommended: "Not recommended",
  ineffective: "Ineffective",
  freshness: "Evidence freshness",
  semanticLosses: "Semantic losses",
  permissions: "Permissions",
  transform: "Transform",
  limitations: "Claim limitations",
  validity: "Claim validity",
  noneListed: "None listed",
  riskInstall: "Local risk install",
  riskInstallBody: "This command runs only in the CLI.",
  copyLabel: "Copy",
  copiedLabel: "Copied",
  copyError: "Copy failed",
  docsLabel: "Docs",
};

const matrix: TargetMatrix = {
  schema_version: 1,
  exact: [
    {
      schema_version: 1,
      kind: "exact",
      harness_id: "claude-code",
      adaptation_id: `adaptation_${"a".repeat(64)}`,
      scope: "global",
      implementation_mode: "native",
      projection_kind: "native_files",
      technical_support: "supported",
      technical_support_reason: null,
      supported_os: ["linux"],
      supported_arch: ["x86_64"],
      semantic_losses: [],
      permissions_summary: [],
      assessment_state: "verified",
      freshness: "2026-09-06T00:00:00.000Z",
      recommendation: "recommended",
      evidence_refs: [],
    },
  ],
  claimed_portable: [
    {
      schema_version: 1,
      kind: "claimed_portable",
      harness_id: "pi",
      claim_id: `claim_${"b".repeat(64)}`,
      transform_family: "portable-source",
      transform_version: "1.0",
      component_types: ["skill"],
      scopes: ["global"],
      limitations: ["lossy"],
      issued_at: "2026-09-06T00:00:00.000Z",
      expires_at: null,
      evidence_refs: [],
      risk_cli_command:
        "ai-stp component risk-install --id component_x --version 1.0 --harness pi --claim-id claim_b",
    },
  ],
};

describe("ComponentTargetMatrix", () => {
  it("labels exact and claimed rows in text and never exposes an install action", () => {
    render(<ComponentTargetMatrix matrix={matrix} labels={labels} />);

    expect(
      screen.getByRole("table", { hidden: true, name: "Harness targets" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Exact targets verified: 1 / 1 (100%)")).toBeInTheDocument();
    expect(screen.getAllByText("Exact projection").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Claimed portable").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Verified").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Supported").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Open projection details: claude-code · native_files").length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("Safety check").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/risk-install/).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /install/i })).not.toBeInTheDocument();
  });
});
