import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { componentSummaryFixture, setupSummaryFixture } from "@/mocks/fixtures/catalog";
import { SEED_A2_SKILL_CORE_ID } from "@/mocks/fixtures/catalog-ids";
import type { ComponentSummary } from "@/lib/api/generated/types.gen";

type Href = string | { pathname: string; query?: Record<string, string> };

vi.mock("@/components/organisms/contact-report-dialog", () => ({
  ContactReportDialog: ({ hideTrigger, open }: { hideTrigger?: boolean; open?: boolean }) =>
    hideTrigger && !open ? null : null,
}));

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({
    href,
    children,
    prefetch,
    ...props
  }: {
    href: Href;
    children?: ReactNode;
    prefetch?: boolean;
  }) => {
    return (
      <a
        href={
          typeof href === "string"
            ? href
            : `${href.pathname}?${new URLSearchParams(href.query ?? {}).toString()}`
        }
        data-prefetch={prefetch === undefined ? "default" : String(prefetch)}
        {...props}
      >
        {children}
      </a>
    );
  },
}));

const { CatalogResults } = await import("@/components/organisms/catalog-results");

const labels = {
  authoritative: "Authoritative",
  experimental: "Experimental",
  experimentalNote: "Unverified — install at your own risk",
  emptyAuthoritative: "No authoritative results",
  emptyExperimental: "No experimental results",
  emptyAll: "No catalog objects match this query.",
  resultsHeading: "Components",
  nextPage: "Next page",
  version: "Version",
  harness: "Harness",
  type: "Type",
  tags: "Tags",
  authorVerified: "Author verified",
  componentVerified: "Component verified",
  yes: "yes",
  no: "no",
  publisher: "Publisher",
  publishedAt: "Published",
  likes: "Likes",
  componentKind: "Component",
  setupKind: "Setup",
};

const authoritative = {
  ...componentSummaryFixture,
  latest_name: "authoritative-component",
  latest_trust: { trust_lane: "authoritative", author_verified: true, component_verified: true },
} as ComponentSummary;

const experimental = {
  ...componentSummaryFixture,
  stable_id: SEED_A2_SKILL_CORE_ID,
  latest_name: "experimental-component",
} as ComponentSummary;

function renderResults(overrides: Partial<Parameters<typeof CatalogResults>[0]> = {}) {
  return render(
    <CatalogResults
      kind="components"
      items={[authoritative]}
      experimental={[experimental]}
      nextCursor={null}
      showExperimental={false}
      basePath="/catalog"
      query={{ resource: "components" }}
      labels={labels}
      {...overrides}
    />,
  );
}

/** REQ-2202: data / empty states. REQ-2208: experimental only on consent. */
describe("CatalogResults", () => {
  it("merges lanes into one results list when experimental is included", () => {
    renderResults({ showExperimental: true });

    expect(screen.getByRole("heading", { name: "Components" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "authoritative-component" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "experimental-component" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "authoritative-component" })).toHaveAttribute(
      "data-prefetch",
      "false",
    );
    expect(screen.getByText("Unverified — install at your own risk")).toBeInTheDocument();
  });

  it("shows the empty state instead of an empty list", () => {
    renderResults({ items: [], experimental: [], showExperimental: true });

    expect(screen.getByText("No catalog objects match this query.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "authoritative-component" })).toBeNull();
  });

  it("hides experimental objects entirely without consent", () => {
    renderResults({ showExperimental: false });

    expect(screen.getByRole("heading", { name: "authoritative-component" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "experimental-component" })).toBeNull();
  });

  it("omits the next-page link when there is no cursor", () => {
    renderResults({ nextCursor: null, showExperimental: true });

    expect(screen.queryByRole("link", { name: "Next page" })).toBeNull();
  });

  it("renders cursor pagination when a next cursor is returned", () => {
    renderResults({ nextCursor: "next-token", query: { q: "python", resource: "components" } });

    const next = screen.getByRole("link", { name: "Next page" });
    expect(next).toHaveAttribute("href", "/catalog?q=python&resource=components&cursor=next-token");
    expect(next).toHaveAttribute("data-prefetch", "false");
  });

  it("renders page counters and preserves filters in page links", () => {
    renderResults({
      totalItems: 51,
      totalPages: 3,
      pageNumber: 2,
      query: { q: "security", resource: "components" },
    });

    expect(screen.getByText("51")).toBeInTheDocument();
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "2" })).toHaveClass("h-11", "min-w-11");
    expect(screen.getByRole("link", { name: "2" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "3" })).toHaveAttribute(
      "href",
      "/catalog?q=security&resource=components&page=3",
    );
  });

  it("uses compact list layout when requested", () => {
    const { container } = renderResults({ view: "list" });
    expect(container.querySelector("ul")).toHaveClass("grid", "min-w-0", "divide-y", "rounded-lg");
    expect(container.querySelector("article[data-view='list']")).not.toBeNull();
  });

  it("renders setup results with locale on the shared card grid", () => {
    const { container } = renderResults({
      kind: "setups",
      items: [setupSummaryFixture],
      experimental: [],
      locale: "ru",
      view: "cards",
      labels: {
        ...labels,
        purpose: "Purpose",
        targetRole: "Role",
        supportTier: "Support tier",
        supportState: "Support state",
        supportEvidence: "Support evidence",
        noSupportEvidence: "No evidence",
      },
    });

    expect(container.querySelector("[data-resource='setups'] ul")).toHaveClass("md:grid-cols-2");
    expect(container.querySelector("article[data-kind='setup']")).not.toBeNull();
    expect(screen.getByRole("link", { name: setupSummaryFixture.latest_name })).toHaveAttribute(
      "href",
      `/catalog/setups/${setupSummaryFixture.stable_id}`,
    );
  });

  it("omits page navigation when the API reports zero pages", () => {
    renderResults({ items: [], experimental: [], totalItems: 0, totalPages: 0 });
    expect(screen.queryByRole("navigation", { name: "Pagination" })).toBeNull();
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("uses one mixed page sequence with setup pages before component pages", () => {
    const { container } = renderResults({
      kind: "mixed",
      items: [componentSummaryFixture, setupSummaryFixture],
      experimental: [],
      pageNumber: 1,
      setupsTotalPages: 2,
      componentsTotalPages: 3,
      query: { resource: "all", view: "list" },
    });
    expect(container.querySelector("article[data-kind='setup']")).toBeInTheDocument();
    expect(container.querySelector("article[data-kind='component']")).not.toBeInTheDocument();
    expect(screen.getAllByRole("navigation", { name: "Pagination" })).toHaveLength(1);
    expect(screen.getByText("1 / 5")).toBeInTheDocument();
  });

  it("moves to the first component page without repeating the final setup page", () => {
    const { container } = renderResults({
      kind: "mixed",
      items: [componentSummaryFixture, setupSummaryFixture],
      experimental: [],
      pageNumber: 3,
      setupsTotalPages: 2,
      componentsTotalPages: 3,
      query: { resource: "all", view: "list" },
    });
    expect(container.querySelector("article[data-kind='setup']")).not.toBeInTheDocument();
    expect(container.querySelector("article[data-kind='component']")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "3" })).toHaveAttribute("aria-current", "page");
  });

  it("maps combined page links to valid resource page numbers", () => {
    renderResults({
      kind: "mixed",
      items: [setupSummaryFixture],
      experimental: [],
      pageNumber: 2,
      setupsTotalPages: 2,
      componentsTotalPages: 3,
      query: { resource: "all", view: "list" },
    });
    expect(screen.getByRole("link", { name: "2" })).toHaveAttribute(
      "href",
      "/catalog?resource=all&view=list&page=2&setups_page=2&components_page=1",
    );
    expect(screen.getByRole("link", { name: "3" })).toHaveAttribute(
      "href",
      "/catalog?resource=all&view=list&page=3&setups_page=2&components_page=1",
    );
    expect(screen.getByRole("link", { name: "5" })).toHaveAttribute(
      "href",
      "/catalog?resource=all&view=list&page=5&setups_page=2&components_page=3",
    );
  });

  it("shows both resource types when page totals are unavailable", () => {
    const { container } = renderResults({
      kind: "mixed",
      items: [componentSummaryFixture, setupSummaryFixture],
      experimental: [],
    });
    const kinds = [...container.querySelectorAll("article")].map((node) =>
      node.getAttribute("data-kind"),
    );
    expect(kinds).toEqual(["setup", "component"]);
  });
});
