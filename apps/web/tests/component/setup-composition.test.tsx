import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SetupComposition } from "@/components/organisms/setup-composition";
import type {
  SetupComponentChecks,
  SetupCompositionMember,
  SetupVersionPassport,
} from "@/lib/api/generated/types.gen";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const labels: Record<string, string> = {
  composition: "Components",
  compositionDescription: "Exact components included in this setup.",
  componentAuthor: "Author",
  componentPublisher: "Published by",
  externalComponent: "Third-party source",
  noneListed: "None listed",
  selectedAdaptation: "Selected harness projection",
  safetyCheck: "Safety check",
  technicalSupport: "Technical support",
  implementationMode: "Implementation",
  recommendation: "Recommendation",
};

const passport = {
  components: [{ stable_id: "component_skill", version: "1.0", passport_digest: "sha256:aa" }],
  facts: {
    component_presentations: {
      value: [
        {
          stable_id: "component_skill",
          version: "1.0",
          name: "Skill Plus",
          component_type: "skill",
          embedded: true,
          source_coordinate: "package:npm:skill-plus@1.0.0",
        },
      ],
    },
  },
} as unknown as SetupVersionPassport;

const components = [
  {
    stable_id: "component_skill",
    version: "1.0",
    name: "Skill Plus",
    embedded: true,
    source_coordinate: "package:npm:skill-plus@1.0.0",
    digest_matches: true,
    failed_mandatory: false,
    checks: [],
  },
] satisfies SetupComponentChecks[];

const composition = [
  {
    schema_version: 1,
    stable_id: "component_skill",
    version: "1.0",
    passport_digest: "sha256:aa",
    selected_adaptation: {
      schema_version: 1,
      adaptation_id: "adaptation_claude",
      harness_id: "claude-code",
      implementation_mode: "native",
      projection_kind: "native_files",
      technical_support: "experimental",
      scopes: ["global"],
      assessment_state: "not_verified",
      recommendation: "ineffective",
      limitations: [],
    },
  },
] satisfies SetupCompositionMember[];

describe("SetupComposition", () => {
  it("presents an external component like a catalog row without safety or token noise", async () => {
    const user = userEvent.setup();
    render(
      <SetupComposition
        passport={passport}
        components={components}
        catalogComponents={[]}
        setupAuthor={{ accountId: "account_author", displayName: "Artem" }}
        t={(key) => labels[key] ?? key}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Components/ }));
    expect(screen.getByText("Skill Plus")).toBeVisible();
    expect(screen.getByText("Third-party source")).toBeVisible();
    expect(screen.getByText(/Published by/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Artem" })).toHaveAttribute(
      "href",
      "/publishers/account_author",
    );
    expect(screen.getByRole("link", { name: "npm" })).toHaveAttribute(
      "href",
      "https://www.npmjs.com/package/skill-plus/v/1.0.0",
    );
    expect(screen.queryByText(/checks passed/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/tokens/i)).not.toBeInTheDocument();
  });

  it("shows the exact selected harness projection and its safety state", async () => {
    const user = userEvent.setup();
    render(
      <SetupComposition
        passport={passport}
        components={components}
        catalogComponents={[]}
        composition={composition}
        setupAuthor={{ accountId: "account_author", displayName: "Artem" }}
        t={(key) => labels[key] ?? key}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Components/ }));
    const projectionSummary = screen.getByText(/Selected harness projection/, {
      selector: "summary",
    });
    await user.click(projectionSummary);
    expect(screen.getByText("Safety check")).toBeVisible();
    expect(screen.getByText("not_verified")).toBeVisible();
    expect(projectionSummary).toHaveTextContent("claude-code");
    expect(projectionSummary).toHaveTextContent("native_files");
  });
});
