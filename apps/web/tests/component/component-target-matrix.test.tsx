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
  summary: "Exact published projections.",
  score: "Exact targets verified",
  harness: "Harness",
  exact: "Exact projection",
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
  noneListed: "None listed",
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
};

describe("ComponentTargetMatrix", () => {
  it("labels exact rows and never exposes a claim or install action", () => {
    render(<ComponentTargetMatrix matrix={matrix} labels={labels} />);

    expect(screen.getByRole("region", { name: "Harness targets" })).toBeInTheDocument();
    expect(screen.getByText("Exact targets verified: 1 / 1 (100%)")).toBeInTheDocument();
    expect(screen.getAllByText("Implementation: native").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Verified").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Supported").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Implementation: native").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Safety check").length).toBeGreaterThan(0);
    expect(screen.queryByText(/risk-install/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /install/i })).not.toBeInTheDocument();
  });
});
