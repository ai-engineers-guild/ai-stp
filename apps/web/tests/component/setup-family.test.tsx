import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({
    children,
    href,
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { prefetch?: boolean }) => (
    <a href={href}>{children}</a>
  ),
}));

import { SetupFamilyBlock } from "@/components/molecules/setup-family";
import type { SetupFamilyPublic } from "@/lib/api/generated/types.gen";

const labels = {
  heading: "Related harness setups",
  summary: "Independent setups grouped for navigation.",
  members: "Family members",
  baseline: "Baseline",
  alignment: "Alignment",
  current: "This setup",
  aligned: "Aligned",
  alignedHint: "Declared invariant matches the family baseline.",
  diverged: "Diverged",
  divergedHint: "Logical inputs differ from the family baseline.",
  unknown: "Unknown",
  unknownHint: "Historical invariant evidence is absent.",
  missing: "Unavailable",
  missingHint: "This member is not available.",
  version: "Version",
  harness: "Harness",
  portedFrom: "Ported from",
  browseFamily: "Browse family in catalog",
};

const family: SetupFamilyPublic = {
  schema_version: 1,
  family_id: "family_demo",
  name: "Demo family",
  created_from: "owner",
  baseline: {
    stable_id: "setup_current",
    version: "1.0",
    passport_digest: `sha256:${"0".repeat(64)}`,
  },
  current_member: null,
  members: [
    {
      schema_version: 1,
      stable_id: "setup_current",
      harness_id: "claude-code",
      latest_version: "1.0",
      exact_version: "1.0",
      passport_digest: `sha256:${"0".repeat(64)}`,
      alignment: "aligned",
      ported_from: null,
    },
    {
      schema_version: 1,
      stable_id: "setup_pi",
      harness_id: "pi",
      latest_version: "1.1",
      exact_version: "1.1",
      passport_digest: `sha256:${"1".repeat(64)}`,
      alignment: "diverged",
      ported_from: {
        stable_id: "setup_current",
        version: "1.0",
        passport_digest: `sha256:${"0".repeat(64)}`,
      },
    },
  ],
};

describe("SetupFamilyBlock", () => {
  it("renders navigational members without write or install controls", () => {
    render(<SetupFamilyBlock family={family} currentStableId="setup_current" labels={labels} />);

    expect(screen.getByText("This setup")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "setup_pi" })).toHaveAttribute(
      "href",
      "/catalog/setups/setup_pi/versions/1.1",
    );
    expect(screen.getByRole("link", { name: "Browse family in catalog" })).toHaveAttribute(
      "href",
      "/catalog?resource=setups&family_id=family_demo",
    );
    expect(screen.getByText(/Alignment: Aligned/)).toBeInTheDocument();
    expect(screen.getByText(/Alignment: Diverged/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText(/sync/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/merge/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/install/i)).not.toBeInTheDocument();
  });
});
