import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CatalogSupport } from "@/lib/api/generated/types.gen";

const { SupportSummary } = await import("@/components/molecules/support-summary");

const labels = {
  tier: "Support tier",
  state: "Support state",
  evidence: "Support evidence",
  noEvidence: "No support evidence",
  result: "Result",
  observedAt: "Observed at",
  expiresAt: "Expires at",
  noExpiry: "No expiry",
};

function support(overrides: Partial<CatalogSupport> = {}): CatalogSupport {
  return {
    schema_version: 1,
    tier: "beta",
    state: "missing",
    evidence: [],
    ...overrides,
  };
}

describe("SupportSummary", () => {
  it("shows the server-projected tier, state, result and timestamps", () => {
    render(
      <SupportSummary
        support={support({
          state: "verified",
          evidence: [
            {
              schema_version: 1,
              check_id: "provider-startup",
              policy_version: "support-v1",
              result: "passed",
              source: "provider_release_evidence",
              provider_id: "opencode",
              provider_version: "1.17.7",
              release_reference: "a".repeat(40),
              operating_system: "linux",
              architecture: "x86_64",
              mandatory: true,
              observed_at: "2026-08-07T12:00:00.000Z",
              expires_at: "2026-09-07T12:00:00.000Z",
            },
          ],
        })}
        labels={labels}
      />,
    );

    expect(screen.getByText("beta")).toBeInTheDocument();
    expect(screen.getByText("verified")).toBeInTheDocument();
    expect(screen.getByText("provider-startup")).toBeInTheDocument();
    expect(screen.getByText(/Result: passed/)).toBeInTheDocument();
    expect(screen.getByText(/Observed at: 2026-08-07T12:00:00.000Z/)).toBeInTheDocument();
    expect(screen.getByText(/Expires at: 2026-09-07T12:00:00.000Z/)).toBeInTheDocument();
  });

  it("does not turn absent evidence into a verified claim", () => {
    render(<SupportSummary support={support()} labels={labels} />);

    expect(screen.getByText("beta")).toBeInTheDocument();
    expect(screen.getByText("missing")).toBeInTheDocument();
    expect(screen.getByText("No support evidence")).toBeInTheDocument();
    expect(screen.queryByText("verified")).toBeNull();
  });
});
