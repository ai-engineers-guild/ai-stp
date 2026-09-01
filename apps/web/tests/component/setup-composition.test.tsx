import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SetupComposition } from "@/components/organisms/setup-composition";
import type { SetupComponentChecks, SetupVersionPassport } from "@/lib/api/generated/types.gen";
import type { SetupContextBudget } from "@/lib/api/catalog";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const labels: Record<string, string> = {
  composition: "Components and safety",
  compositionDescription: "Exact versions and safety",
  componentAuthor: "Author",
  componentSource: "Source",
  embeddedSnapshot: "Embedded snapshot",
  catalogComponent: "Catalog component",
  requiredChecksPassed: "Required checks passed",
  requiredChecksFailed: "Required checks failed",
  reviewChecks: "Review checks",
  safetyNoScan: "No checks yet",
  safetyChecksComplete: "checks passed",
  safetyFailed: "Failed checks",
  safetyWarning: "Warnings",
  safetyNotRun: "Not run",
  contextBudgetError: "Unavailable",
  contextBudgetTokens: "tokens",
  contextBudgetAlways: "Always loaded",
  contextBudgetConditional: "Loaded when used",
  contextBudgetRuntimeDerived: "Runtime-derived",
  embeddedSnapshotHint: "Not published separately",
  noneListed: "None listed",
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
        },
      ],
    },
  },
} as unknown as SetupVersionPassport;

const checks: SetupComponentChecks[] = [
  {
    stable_id: "component_skill",
    version: "1.0",
    name: "Skill Plus",
    embedded: true,
    source_coordinate: "package:npm:skill-plus@1.0.0",
    digest_matches: true,
    failed_mandatory: false,
    checks: [
      {
        schema_version: 1,
        check_id: "structure",
        result: "passed",
        mandatory: true,
        source: "scan",
        family: "",
        reason: null,
        finding_summary: null,
      },
      {
        schema_version: 1,
        check_id: "license",
        result: "passed",
        mandatory: true,
        source: "scan",
        family: "",
        reason: null,
        finding_summary: null,
      },
      {
        schema_version: 1,
        check_id: "sast_opengrep",
        result: "failed",
        mandatory: false,
        source: "scan",
        family: "",
        reason: null,
        finding_summary: null,
      },
    ],
  },
];

const budget = {
  schema_version: 1,
  coordinate: { stable_id: "setup_a", version: "1.0", passport_digest: "sha256:ss" },
  estimator: { profile: "ai-stp:utf8-bytes/1", accuracy: "exact", method: "utf8_byte_count" },
  always_tokens: 0,
  conditional_tokens: 800,
  total_tokens: 800,
  unavailable_components: 0,
  status: "ready",
  components: [
    {
      component: { stable_id: "component_skill", version: "1.0", passport_digest: "sha256:aa" },
      component_type: "skill",
      loading: "conditional",
      status: "exact",
      tokens: 800,
      utf8_bytes: 800,
    },
  ],
} satisfies SetupContextBudget;

describe("SetupComposition", () => {
  it("shows component identity, origin, author, source, safety total, and context", async () => {
    const user = userEvent.setup();
    render(
      <SetupComposition
        passport={passport}
        components={checks}
        catalogComponents={[]}
        setupAuthor={{ accountId: "account_author", displayName: "Artem" }}
        budget={budget}
        t={(key) => labels[key] ?? key}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Components and safety/ }));
    expect(screen.getByText("Skill Plus")).toBeVisible();
    expect(screen.getByText("skill")).toBeVisible();
    expect(screen.getByText("Embedded snapshot")).toBeVisible();
    expect(screen.getByRole("link", { name: "Artem" })).toHaveAttribute(
      "href",
      "/publishers/account_author",
    );
    expect(screen.getByRole("link", { name: "npmjs.com" })).toBeVisible();
    expect(screen.getByText("Required checks passed")).toBeVisible();
    expect(screen.getByText(/2\/3 checks passed/)).toBeVisible();
    expect(screen.getByText(/800 tokens/)).toBeVisible();
  });
});
