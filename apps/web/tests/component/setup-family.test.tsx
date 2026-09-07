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
vi.mock("@/components/organisms/contact-report-dialog", () => ({
  ContactReportDialog: () => null,
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
  setup: "Setup",
  parent: "Parent setup",
  recast: "Recast setup",
  moreActions: "More actions",
  copyUrl: "Copy URL",
  copyCli: "Copy CLI command",
  copyId: "Copy ID",
  copied: "Copied",
  like: "Like",
  unlike: "Unlike",
  report: "Report setup",
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
      name: "Current setup",
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
      name: "Pi setup",
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

    expect(screen.getByText("Parent setup · Family members: 2")).toBeInTheDocument();
    screen.getByRole("heading", { name: "Related harness setups" }).closest("summary")?.click();
    expect(screen.getByText("This setup")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Pi setup" })).toHaveAttribute(
      "href",
      "/catalog/setups/setup_pi/versions/1.1",
    );
    expect(screen.getAllByRole("button", { name: "More actions" })).toHaveLength(2);
    expect(screen.queryByText(/sync/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/merge/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/install/i)).not.toBeInTheDocument();
  });

  it("shows the port source on the family card and exposes working row actions", () => {
    render(
      <SetupFamilyBlock
        family={family}
        currentStableId="setup_pi"
        portedFrom={family.members[1]?.ported_from ?? null}
        labels={labels}
      />,
    );

    expect(screen.getByText("Recast setup · Family members: 2")).toBeInTheDocument();
    screen.getByRole("heading", { name: "Related harness setups" }).closest("summary")?.click();
    expect(screen.getByText(/Ported from/)).toBeInTheDocument();
    expect(
      screen
        .getAllByRole("link", { name: "Current setup" })
        .some((link) => link.getAttribute("href") === "/catalog/setups/setup_current/versions/1.0"),
    ).toBe(true);
    expect(screen.getAllByRole("button", { name: "More actions" })).toHaveLength(2);
  });
});
