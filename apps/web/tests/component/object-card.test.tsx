/* eslint-disable max-lines -- Object-card variants share one fixture and mock harness. */
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { ComponentSummary } from "@/lib/api/generated/types.gen";
import { componentSummaryFixture } from "@/mocks/fixtures/catalog";

vi.mock("@/lib/features/gate", () => ({
  isFeatureEnabled: (key: string) => key === "catalog_usage_metrics",
}));

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ href, children }: { href: string; children?: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/components/organisms/contact-report-dialog", () => ({
  ContactReportDialog: ({
    label,
    hideTrigger,
    open,
  }: {
    label: string;
    hideTrigger?: boolean;
    open?: boolean;
  }) => (hideTrigger && !open ? null : <button type="button">{label}</button>),
}));

const { ObjectCard } = await import("@/components/organisms/object-card");
const labels = {
  harness: "Harness",
  tags: "Tags",
  likes: "Likes",
  componentKind: "Component",
  setupKind: "Setup",
  publisher: "Publisher",
  authorVerified: "Author verified",
  authorVerifiedDescription: "Author identity verified; this does not indicate content safety",
  requirements: "Requirements",
  credentialsRequired: "credentials required",
  githubStars: "GitHub stars",
};

function checks(warning: number, failed = 0) {
  return {
    schema_version: 1 as const,
    status: "available" as const,
    checks: [],
    checks_passed_percent: 0,
    coverage_complete: true,
    failed,
    not_run: 0,
    passed: 0,
    total_countable: warning + failed,
    warning,
  };
}

describe("ObjectCard compact catalog presentation (REQ-3411)", () => {
  it("renders only the requested list identity and facets", () => {
    const { container } = render(
      <ObjectCard
        kind="component"
        item={componentSummaryFixture}
        href="/catalog/x"
        labels={labels}
        view="list"
        author={{ displayName: "River Guild", avatarUrl: null }}
      />,
    );
    expect(
      screen.getByRole("heading", { name: componentSummaryFixture.latest_name }),
    ).toBeInTheDocument();
    expect(screen.getByText(componentSummaryFixture.latest_component_type)).toBeInTheDocument();
    expect(screen.getByText(componentSummaryFixture.latest_harness_id)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /River Guild/ })).toHaveAttribute(
      "href",
      `/publishers/${componentSummaryFixture.publisher_id}`,
    );
    expect(container).not.toHaveTextContent(componentSummaryFixture.publisher_id);
    expect(container).not.toHaveTextContent(componentSummaryFixture.latest_description);
    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.querySelector("article > div")).toHaveClass(
      "grid",
      "min-w-0",
      "items-start",
      "gap-x-3",
    );
    expect(container.querySelector("article")).toHaveClass("min-w-0", "overflow-x-hidden");
    expect(container.querySelector("article")).toHaveAttribute("data-view", "list");
    expect(screen.getByRole("button", { name: "More actions" })).toHaveClass("h-11", "w-11");
  });

  it("renders the richer card without duplicated metadata", () => {
    const { container } = render(
      <ObjectCard
        kind="component"
        item={{ ...componentSummaryFixture, likes_count: 4 }}
        href="/catalog/x"
        labels={labels}
        view="cards"
        author={{ displayName: "River Guild", avatarUrl: null }}
      />,
    );
    expect(screen.getByText(componentSummaryFixture.latest_description)).toBeInTheDocument();
    expect(screen.getByLabelText("Likes: 4")).toBeInTheDocument();
    expect(screen.getAllByText(componentSummaryFixture.latest_component_type)).toHaveLength(1);
    expect(container).not.toHaveTextContent("Author verified");
    expect(container).not.toHaveTextContent("Support tier");
    expect(container.querySelector("article")).toHaveClass(
      "h-full",
      "min-w-0",
      "overflow-x-hidden",
    );
    expect(container.querySelector("article")).toHaveAttribute("data-view", "cards");
    expect(screen.getByRole("button", { name: "More actions" })).toHaveClass("h-11", "w-11");
  });

  it("marks a currently verified author independently from content verification", () => {
    render(
      <ObjectCard
        kind="component"
        item={{
          ...componentSummaryFixture,
          latest_trust: {
            ...componentSummaryFixture.latest_trust,
            author_verified: true,
            component_verified: false,
          },
        }}
        href="/catalog/x"
        labels={labels}
        author={{ displayName: "River Guild", avatarUrl: null }}
      />,
    );
    expect(
      screen.getByLabelText("Author identity verified; this does not indicate content safety"),
    ).toBeVisible();
    expect(screen.queryByText("Component verified")).not.toBeInTheDocument();
  });

  it("shows cached GitHub stars without presenting them as trust", () => {
    render(
      <ObjectCard
        kind="component"
        item={{ ...componentSummaryFixture, github_stars: 42 }}
        href="/catalog/x"
        labels={labels}
        view="cards"
      />,
    );
    expect(screen.getByLabelText("GitHub stars: 42")).toBeVisible();
    expect(
      screen.queryByLabelText("Author identity verified; this does not indicate content safety"),
    ).not.toBeInTheDocument();
  });

  it("shows compact requirements without exposing credential values", () => {
    render(
      <ObjectCard
        kind="component"
        item={{
          ...componentSummaryFixture,
          latest_requirements_count: 3,
          latest_requires_credentials: true,
        }}
        href="/catalog/x"
        labels={labels}
        view="cards"
      />,
    );
    expect(screen.getByText("Requirements: 3 · credentials required")).toBeVisible();
    expect(screen.queryByText(/secret/i)).not.toBeInTheDocument();
  });

  it("keeps the author block off the title row and still shows a real zero likes count", () => {
    const { container } = render(
      <ObjectCard
        kind="component"
        item={{ ...componentSummaryFixture, likes_count: 0, github_stars: null }}
        href="/catalog/x"
        labels={labels}
        view="list"
        author={{ displayName: "River Guild", avatarUrl: null }}
      />,
    );
    const author = screen.getByRole("link", { name: /River Guild/ });
    const titleRow = screen.getByRole("heading", {
      name: componentSummaryFixture.latest_name,
    }).parentElement;
    expect(author).toBeInTheDocument();
    expect(titleRow).not.toBeNull();
    expect(titleRow).not.toContainElement(author);
    expect(screen.getByLabelText("Likes: 0")).toBeInTheDocument();
    expect(screen.queryByLabelText(/GitHub stars:/)).not.toBeInTheDocument();
    expect(container.querySelector('[role="meter"]')).toHaveAttribute(
      "title",
      expect.stringContaining("Safety check"),
    );
  });

  it("shows a zero GitHub star cache and never invents stars when they are missing", () => {
    const { rerender } = render(
      <ObjectCard
        kind="setup"
        item={{ ...componentSummaryFixture, github_stars: 0, likes_count: 2 }}
        href="/catalog/x"
        labels={{ ...labels, setupKind: undefined, reportSetup: "Report setup" }}
        view="cards"
      />,
    );
    expect(screen.getByLabelText("GitHub stars: 0")).toBeVisible();
    rerender(
      <ObjectCard
        kind="setup"
        item={{ ...componentSummaryFixture, github_stars: null, likes_count: 2 }}
        href="/catalog/x"
        labels={{ ...labels, reportSetup: "Report setup" }}
        view="cards"
      />,
    );
    expect(screen.queryByLabelText(/GitHub stars:/)).not.toBeInTheDocument();
  });

  it("shows a single percentage safety score with an accessible meter", () => {
    const explanation =
      "Safety check: a set of automated checks that this component does not threaten the user's agent or device.";
    const { container } = render(
      <ObjectCard
        kind="component"
        item={{
          ...componentSummaryFixture,
          latest_checks: {
            schema_version: 1,
            status: "available",
            checks_passed_percent: 50,
            coverage_complete: false,
            passed: 2,
            failed: 1,
            warning: 1,
            not_run: 2,
            total_countable: 6,
            checks: [],
          },
        }}
        href="/catalog/x"
        labels={{
          ...labels,
          safetyCheckExplanation: explanation,
          safetyChecks: "Safety checks",
          safetyPassed: "passed",
          safetyFailed: "failed",
          safetyWarning: "warning",
          safetyNotRun: "not run",
        }}
        view="list"
      />,
    );
    expect(screen.getByText("50%")).toBeVisible();
    const meter = screen.getByRole("meter", { name: `${explanation} 50%` });
    expect(meter).toHaveAttribute("aria-valuenow", "50");
    expect(meter).toHaveAttribute("title", explanation);
    const fill = container.querySelector("[data-safety-fill]");
    expect(fill).toHaveStyle({ width: "50%" });
    expect(fill?.firstElementChild).toHaveStyle({
      background:
        "linear-gradient(90deg, hsl(var(--destructive)), hsl(var(--warning)), hsl(var(--success)))",
    });
    expect(screen.queryByText("1 warning")).not.toBeInTheDocument();
  });

  it("does not render a false 0/0 score when checks were not run", () => {
    render(
      <ObjectCard
        kind="component"
        item={{
          ...componentSummaryFixture,
          latest_checks: {
            schema_version: 1,
            status: "empty",
            checks_passed_percent: null,
            coverage_complete: true,
            passed: 0,
            failed: 0,
            warning: 0,
            not_run: 0,
            total_countable: 0,
            checks: [],
          },
        }}
        href="/catalog/x"
        labels={{ ...labels, safetyNoScan: "Not scanned" }}
        view="cards"
      />,
    );
    expect(screen.getByText("Not scanned")).toBeVisible();
    expect(screen.queryByText("0/0")).not.toBeInTheDocument();
  });

  it("adds a short why-open line when checks failed and keeps likes in both views", () => {
    const item: ComponentSummary = {
      ...componentSummaryFixture,
      likes_count: 4,
      github_stars: 9,
      latest_checks: {
        checks: componentSummaryFixture.latest_checks?.checks ?? [],
        coverage_complete: componentSummaryFixture.latest_checks?.coverage_complete ?? true,
        schema_version: 1,
        status: componentSummaryFixture.latest_checks?.status ?? "available",
        failed: 2,
        warning: 0,
        not_run: 0,
        passed: 4,
        total_countable: 6,
        checks_passed_percent: 67,
      },
    };
    const { rerender } = render(
      <ObjectCard
        kind="component"
        item={item}
        href="/catalog/x"
        labels={{ ...labels, whyFailed: "Failed checks - review before use" }}
        view="list"
        author={{ displayName: "River Guild", avatarUrl: null }}
      />,
    );
    expect(screen.getByText("Failed checks - review before use")).toHaveAttribute("data-why-open");
    expect(screen.getByLabelText("Likes: 4")).toBeVisible();
    expect(screen.getByLabelText("GitHub stars: 9")).toBeVisible();
    rerender(
      <ObjectCard
        kind="component"
        item={item}
        href="/catalog/x"
        labels={{ ...labels, whyFailed: "Failed checks - review before use" }}
        view="cards"
        author={{ displayName: "River Guild", avatarUrl: null }}
      />,
    );
    expect(screen.getByText("Failed checks - review before use")).toBeVisible();
    expect(screen.getByLabelText("Likes: 4")).toBeVisible();
    expect(screen.getByLabelText("GitHub stars: 9")).toBeVisible();
  });

  it("falls back to warning, credentials and list-description why-open copy", () => {
    const { rerender } = render(
      <ObjectCard
        kind="component"
        item={{ ...componentSummaryFixture, latest_checks: checks(2) }}
        href="/catalog/x"
        labels={labels}
        view="cards"
      />,
    );
    expect(screen.getByText("2 warnings")).toBeVisible();
    rerender(
      <ObjectCard
        kind="component"
        item={{
          ...componentSummaryFixture,
          latest_checks: null,
          latest_requires_credentials: true,
        }}
        href="/catalog/x"
        labels={{ harness: "Harness", tags: "Tags", likes: "Likes" }}
        view="cards"
      />,
    );
    expect(screen.getByText("credentials required")).toBeVisible();
    rerender(
      <ObjectCard
        kind="component"
        item={{
          ...componentSummaryFixture,
          latest_checks: null,
          latest_requires_credentials: false,
          latest_description: "  short why  ",
        }}
        href="/catalog/x"
        labels={labels}
        view="list"
      />,
    );
    expect(screen.getByText("short why")).toBeVisible();
    rerender(
      <ObjectCard
        kind="component"
        item={{
          ...componentSummaryFixture,
          latest_checks: null,
          latest_requires_credentials: false,
          latest_description: "   ",
        }}
        href="/catalog/x"
        labels={labels}
        view="list"
      />,
    );
    expect(screen.queryByTestId("why-open")).not.toBeInTheDocument();
    expect(screen.queryByText("short why")).not.toBeInTheDocument();
  });

  it("uses fallback report and derived safety percent for setups", () => {
    render(
      <ObjectCard
        kind="setup"
        item={{
          ...componentSummaryFixture,
          latest_checks: {
            schema_version: 1,
            status: "available",
            checks_passed_percent: null,
            coverage_complete: true,
            passed: 1,
            failed: 1,
            warning: 0,
            not_run: 0,
            total_countable: 2,
            checks: [
              {
                schema_version: 1,
                check_id: "a",
                result: "passed",
                mandatory: true,
                source: "platform_safety_scan",
                family: "x",
                reason: null,
                finding_summary: null,
              },
              {
                schema_version: 1,
                check_id: "b",
                result: "failed",
                mandatory: true,
                source: "platform_safety_scan",
                family: "x",
                reason: null,
                finding_summary: null,
              },
            ],
          },
        }}
        href="/catalog/x"
        labels={{ ...labels, safetyChecks: "Safety checks" }}
        view="cards"
      />,
    );
    expect(
      screen.getByRole("meter", {
        name: /Safety check: a set of automated checks that this component does not threaten the user's agent or device\. 50%/,
      }),
    ).toBeInTheDocument();
  });

  it("shows every named harness on the card", () => {
    render(
      <ObjectCard
        kind="component"
        item={{
          ...componentSummaryFixture,
          latest_harness_id: "claude-code",
          latest_harness_ids: ["claude-code", "codex", "grok-build"],
        }}
        href="/catalog/x"
        labels={labels}
        view="list"
      />,
    );
    expect(screen.getByText("claude-code")).toBeVisible();
    expect(screen.getByText("codex")).toBeVisible();
    expect(screen.getByText("grok-build")).toBeVisible();
  });

  it("shows card usage metrics only when the API sent an aggregate", () => {
    const { rerender } = render(
      <ObjectCard
        kind="component"
        item={{
          ...componentSummaryFixture,
          usage_metrics: { schema_version: 1, detail_views_count: 5, artifact_downloads_count: 1 },
        }}
        href="/catalog/x"
        labels={{ ...labels, detailViews: "Detail views", artifactDownloads: "Artifact downloads" }}
        view="list"
      />,
    );
    expect(screen.getByLabelText("Detail views: 5")).toBeInTheDocument();
    expect(screen.getByLabelText("Artifact downloads: 1")).toBeInTheDocument();
    rerender(
      <ObjectCard
        kind="component"
        item={{ ...componentSummaryFixture, usage_metrics: null }}
        href="/catalog/x"
        labels={{ ...labels, detailViews: "Detail views", artifactDownloads: "Artifact downloads" }}
        view="list"
      />,
    );
    expect(screen.queryByLabelText(/Detail views:/)).not.toBeInTheDocument();
  });
});
