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

  it("renders setups before components in mixed resource mode", () => {
    const { container } = renderResults({
      kind: "mixed",
      items: [componentSummaryFixture, setupSummaryFixture],
      experimental: [],
      view: "list",
    });
    const articles = container.querySelectorAll("article");
    expect(articles).toHaveLength(2);
    expect(articles[0]).toHaveAttribute("data-kind", "setup");
    expect(articles[1]).toHaveAttribute("data-kind", "component");
    expect(container.querySelector("article[data-kind='setup']")).toHaveClass("bg-muted/50");
    expect(container.querySelectorAll("section[data-resource='mixed'] > ul")).toHaveLength(1);
    expect(screen.queryByRole("heading", { name: "Setup" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Component" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: setupSummaryFixture.latest_name })).toHaveAttribute(
      "href",
      `/catalog/setups/${setupSummaryFixture.stable_id}`,
    );
  });

  it("keeps mixed card items on the same grid track width", () => {
    const { container } = renderResults({
      kind: "mixed",
      items: [componentSummaryFixture, setupSummaryFixture],
      experimental: [],
      view: "cards",
    });

    const items = container.querySelectorAll("ul > li");
    expect(items).toHaveLength(2);
    items.forEach((item) => {
      expect(item).toHaveClass("min-w-0");
      expect(item).not.toHaveClass("sm:col-span-2", "lg:col-span-2");
      expect(item.querySelector("article")).toHaveClass("h-full");
    });
    expect(container.querySelector("article[data-kind='setup']")).toHaveClass("bg-muted/50");
    expect(container.querySelector("article[data-kind='component']")).not.toHaveClass(
      "bg-muted/50",
    );
  });

  it("shows component pagination after the setup sequence is complete", () => {
    renderResults({
      kind: "mixed",
      items: [componentSummaryFixture, setupSummaryFixture],
      experimental: [],
      setupsTotalPages: 1,
      setupsPageNumber: 1,
      componentsTotalPages: 3,
      componentsPageNumber: 2,
    });
    expect(screen.getByRole("navigation", { name: "Components pagination" })).toBeInTheDocument();
  });

  it("paginates components when setup pages are absent", () => {
    renderResults({
      kind: "mixed",
      items: [componentSummaryFixture, setupSummaryFixture],
      experimental: [],
      componentsTotalPages: 2,
      componentsPageNumber: 1,
    });
    expect(screen.getByRole("navigation", { name: "Components pagination" })).toBeInTheDocument();
  });

  it("defaults omitted mixed pagination positions to the first page", () => {
    renderResults({
      kind: "mixed",
      items: [componentSummaryFixture, setupSummaryFixture],
      experimental: [],
      setupsTotalPages: 2,
      componentsTotalPages: 2,
    });
    expect(screen.getByRole("navigation", { name: "Setups pagination" })).toBeInTheDocument();
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("defaults omitted component and setup positions after setup pagination", () => {
    renderResults({
      kind: "mixed",
      items: [componentSummaryFixture],
      experimental: [],
      componentsTotalPages: 2,
    });
    expect(screen.getByRole("navigation", { name: "Components pagination" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "2" })).toHaveAttribute(
      "href",
      "/catalog?resource=components&page=1&components_page=2&setups_page=1",
    );
  });

  it("shows setup pagination before the component sequence starts", () => {
    renderResults({
      kind: "mixed",
      items: [componentSummaryFixture, setupSummaryFixture],
      experimental: [],
      setupsTotalPages: 4,
      setupsPageNumber: 2,
      componentsTotalPages: 3,
      componentsPageNumber: 1,
    });
    expect(screen.getByRole("navigation", { name: "Setups pagination" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Components pagination" })).toBeNull();
  });

  it("does not render an empty group when only one resource matches", () => {
    renderResults({
      kind: "mixed",
      items: [componentSummaryFixture],
      experimental: [],
      labels: {
        ...labels,
        setupsHeading: "Setups",
        componentsHeading: "Components",
        emptySetups: "No setups match this query.",
      },
    });
    expect(screen.queryByRole("heading", { name: "Setups" })).not.toBeInTheDocument();
    expect(screen.queryByText("No setups match this query.")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: componentSummaryFixture.latest_name }),
    ).toBeInTheDocument();
  });

  it("keeps each mixed group in the order supplied by its own result set", () => {
    const firstSetup = {
      ...setupSummaryFixture,
      stable_id: "setup_first",
      latest_name: "setup-first",
    };
    const secondSetup = {
      ...setupSummaryFixture,
      stable_id: "setup_second",
      latest_name: "setup-second",
    };
    const firstComponent = {
      ...componentSummaryFixture,
      stable_id: "cmp_first",
      latest_name: "component-first",
    };
    const secondComponent = {
      ...componentSummaryFixture,
      stable_id: "cmp_second",
      latest_name: "component-second",
    };
    const { container } = renderResults({
      kind: "mixed",
      items: [firstComponent, firstSetup, secondComponent, secondSetup],
      experimental: [],
    });
    const names = [...container.querySelectorAll("article h3")].map((node) => node.textContent);
    expect(names).toEqual(["setup-first", "setup-second", "component-first", "component-second"]);
  });

  it("does not expose components before the final setup page", () => {
    const { container } = renderResults({
      kind: "mixed",
      items: [componentSummaryFixture, setupSummaryFixture],
      experimental: [],
      nextCursor: "should-not-be-used",
      setupsPageNumber: 1,
      componentsPageNumber: 2,
      setupsTotalPages: 2,
      componentsTotalPages: 3,
      query: { resource: "all", view: "list" },
      labels: { ...labels, setupsHeading: "Setups", componentsHeading: "Components" },
    });
    expect(screen.queryByRole("link", { name: "Next page" })).toBeNull();
    expect(screen.getByRole("navigation", { name: "Setups pagination" })).toBeInTheDocument();
    expect(container.querySelector("article[data-kind='setup']")).toBeInTheDocument();
    expect(container.querySelector("article[data-kind='component']")).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Components pagination" })).toBeNull();
    const pagers = screen.getAllByRole("navigation", { name: /pagination/i });
    expect(pagers).toHaveLength(1);
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
    const setupPageTwo = pagers[0]?.querySelector('a[href*="setups_page=2"]');
    expect(setupPageTwo?.getAttribute("href")).toContain("components_page=1");
    expect(setupPageTwo?.getAttribute("href")).not.toContain("cursor=");
  });

  it("joins the first component page to the final setup page", () => {
    const { container } = renderResults({
      kind: "mixed",
      items: [componentSummaryFixture, setupSummaryFixture],
      experimental: [],
      setupsPageNumber: 2,
      componentsPageNumber: 1,
      setupsTotalPages: 2,
      componentsTotalPages: 3,
    });
    const kinds = [...container.querySelectorAll("article")].map((node) =>
      node.getAttribute("data-kind"),
    );
    expect(kinds).toEqual(["setup", "component"]);
    expect(screen.getByRole("navigation", { name: "Components pagination" })).toBeInTheDocument();
  });

  it("continues with components without repeating setups", () => {
    const { container } = renderResults({
      kind: "mixed",
      items: [componentSummaryFixture, setupSummaryFixture],
      experimental: [],
      setupsPageNumber: 2,
      componentsPageNumber: 2,
      setupsTotalPages: 2,
      componentsTotalPages: 3,
    });
    expect(container.querySelector("article[data-kind='setup']")).not.toBeInTheDocument();
    expect(container.querySelector("article[data-kind='component']")).toBeInTheDocument();
  });

  it("windows long independent page controls under the single mixed list", () => {
    renderResults({
      kind: "mixed",
      items: [componentSummaryFixture, setupSummaryFixture],
      experimental: [],
      setupsPageNumber: 10,
      componentsPageNumber: 1,
      setupsTotalPages: 20,
      componentsTotalPages: 20,
      setupsTotalItems: 48,
      componentsTotalItems: 112,
      labels: { ...labels, setupsHeading: "Setups", componentsHeading: "Components" },
    });
    expect(screen.getByRole("region").querySelector("[aria-live='polite']")).toHaveTextContent("1");
    expect(screen.getByRole("link", { name: "10" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: "15" })).toBeNull();
    expect(screen.getAllByText("…").length).toBeGreaterThan(0);
  });
});
