/* eslint-disable max-lines -- Catalog filter interactions share one expensive UI harness. */
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { ParsedCatalogQuery } from "@/lib/catalog-query";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ href, children, ...props }: { href: string; children?: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
  usePathname: () => "/catalog",
  useRouter: () => ({ push: vi.fn() }),
}));

const { CatalogFilters } = await import("@/components/organisms/catalog-filters");

const labels = {
  search: "Search",
  searchPlaceholder: "Search…",
  searchHelp: "Search help",
  resourceLegend: "Catalog resource",
  components: "Components",
  setups: "Setups",
  resourceBoth: "Both",
  experimentalConsent: "Include experimental",
  tagFilter: "Tag",
  harnessFilter: "Harness",
  typeFilter: "Component type",
  supportTierFilter: "Support tier",
  supportStateFilter: "Support state",
  anyOption: "Any",
  applyFilters: "Apply filters",
  filtersButton: "Filters",
  resetAll: "Reset all",
  filterHelpTitle: "About filters",
  filterHelpBody: "Filter help",
  dismissFilter: "Remove filter",
  closeFilters: "Close",
  filterHelpLabel: "Help for filter",
  tagFilterHelp: "Help for tags",
  harnessFilterHelp: "Help for harnesses",
  typeFilterHelp: "Help for component types",
  authorFilterHelp: "Help for authors",
  verifiedOnlyHelp: "Help for verified only",
  countryFilterHelp: "Help for countries",
  serviceFilterHelp: "Help for services",
  updatedRangeHelp: "Help for update dates",
  searchOptions: "Search options",
  authorFilter: "Author",
  verifiedOnly: "Only verified",
  serviceFilter: "External service domain",
  countryFilter: "Country code",
  sortBy: "Sort results",
  sortDirection: "Direction",
  sortRelevance: "Relevance",
  sortUpdated: "Recently updated",
  sortLikes: "Most liked",
  sortAscending: "Ascending",
  sortDescending: "Descending",
  viewLabel: "Result layout",
  cardsView: "Cards",
  listView: "List",
};

function query(overrides: Partial<ParsedCatalogQuery> = {}): ParsedCatalogQuery {
  return {
    q: "",
    resource: "all",
    includeExperimental: true,
    pageSize: 25,
    pageNumber: 1,
    cursor: undefined,
    tags: [],
    harnessId: undefined,
    componentType: undefined,
    harnessIds: [],
    componentTypes: [],
    authors: [],
    verifiedOnly: false,
    sort: "relevance",
    sortDirection: "desc",
    view: "list",
    supportTier: undefined,
    supportState: undefined,
    ...overrides,
  };
}

describe("CatalogFilters", () => {
  it("keeps reset chips and filter counts absent for the default query", async () => {
    const user = userEvent.setup();
    render(
      <CatalogFilters query={query({ resource: "components", view: "cards" })} labels={labels} />,
    );
    expect(screen.getByRole("button", { name: "Search" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Catalog resource" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Reset all" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Filters" }));
    expect(screen.getByRole("combobox", { name: "Catalog resource" })).toHaveValue("components");
    expect(screen.getByRole("option", { name: "Both" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(screen.getByRole("button", { name: "Filters" })).toBeInTheDocument();
  });

  it("renders resource and supported facet filters without removed support controls", async () => {
    const user = userEvent.setup();
    render(
      <CatalogFilters
        query={query({
          resource: "components",
          harnessIds: ["codex"],
          componentTypes: ["skill"],
          view: "cards",
        })}
        labels={labels}
      />,
    );
    await user.click(screen.getByRole("button", { name: /^Filters/ }));
    expect(screen.getByRole("combobox", { name: "Catalog resource" })).toHaveValue("components");
    expect(screen.queryByRole("checkbox", { name: /Include experimental/i })).toBeNull();
    expect(screen.getByRole("group", { name: /Tag/ })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Harness" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Component type" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "codex" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "skill" })).toBeChecked();
    expect(screen.queryByRole("combobox", { name: "Support tier" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Support state" })).toBeNull();
    expect(screen.getByRole("button", { name: "Apply filters" })).toBeInTheDocument();
  });

  it("hides component type facet for setups resource", async () => {
    const user = userEvent.setup();
    render(
      <CatalogFilters
        query={query({
          q: "python",
          resource: "setups",
          tags: ["python"],
          serviceDomains: ["example.com"],
          view: "cards",
        })}
        labels={labels}
      />,
    );
    await user.click(screen.getByRole("button", { name: /^Filters/ }));
    expect(screen.queryByLabelText("Component type")).toBeNull();
    expect(screen.getByRole("combobox", { name: "Catalog resource" })).toHaveValue("setups");
  });

  it("shows applied filter count and dismissible chips with reset in the popup", async () => {
    const user = userEvent.setup();
    render(
      <CatalogFilters
        query={query({
          resource: "components",
          includeExperimental: false,
          tags: ["python", "security"],
          harnessId: "codex",
          view: "cards",
        })}
        labels={labels}
      />,
    );
    expect(screen.getByRole("button", { name: "Filters (4)" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /python/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /security/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /codex/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Filters (4)" }));
    expect(screen.getByRole("link", { name: "Reset all" })).toBeInTheDocument();
  });

  it("opens separate sort and view popup controls", async () => {
    const user = userEvent.setup();
    render(
      <CatalogFilters
        query={query({
          q: "NAME:guard",
          resource: "components",
          pageNumber: 4,
          tags: ["python"],
          verifiedOnly: true,
          view: "cards",
        })}
        labels={labels}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Result layout" }));
    expect(screen.getByRole("menuitem", { name: /Cards/ })).toHaveAttribute("aria-current", "true");
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Sort results" }));
    expect(screen.getByRole("menuitem", { name: "Relevance" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByRole("menuitem", { name: "Descending" })).toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  it("opens search and filter panels independently with search first", async () => {
    const user = userEvent.setup();
    render(<CatalogFilters query={query()} labels={labels} />);
    await user.click(screen.getByRole("button", { name: "Search" }));
    await user.click(screen.getByRole("button", { name: "Filters" }));
    const search = document.getElementById("catalog-text-search");
    const filters = document.getElementById("catalog-refine");
    expect(search).not.toBeNull();
    expect(filters).not.toBeNull();
    expect(
      Boolean(
        search &&
        filters &&
        search.compareDocumentPosition(filters) & Node.DOCUMENT_POSITION_FOLLOWING,
      ),
    ).toBe(true);
    expect(screen.getByRole("button", { name: "Search", expanded: true })).toHaveAttribute(
      "aria-controls",
      "catalog-text-search",
    );
    expect(screen.getByRole("button", { name: "Filters", expanded: true })).toHaveAttribute(
      "aria-controls",
      "catalog-refine",
    );
    await user.keyboard("{Escape}");
    expect(document.getElementById("catalog-refine")).toBeNull();
    expect(document.getElementById("catalog-text-search")).not.toBeNull();
  });

  it("closes an open toolbar panel from its Escape shortcut", async () => {
    const user = userEvent.setup();
    render(<CatalogFilters query={query()} labels={labels} />);
    const filters = screen.getByRole("button", { name: "Filters" });
    fireEvent.keyDown(filters, { key: "Escape" });
    await user.click(filters);
    fireEvent.keyDown(filters, { key: "ArrowDown" });
    expect(document.getElementById("catalog-refine")).not.toBeNull();
    fireEvent.keyDown(filters, { key: "Escape" });
    expect(document.getElementById("catalog-refine")).toBeNull();
  });

  it("keeps country and service filters linked and offers an unspecified choice", async () => {
    const user = userEvent.setup();
    render(
      <CatalogFilters
        query={query()}
        labels={{
          ...labels,
          unspecifiedOption: "Not specified",
          refineButton: "Filters & sorting",
        }}
        services={[
          {
            schema_version: 1,
            name: "Kaspi",
            canonical_domain: "kaspi.kz",
            primary_url: "https://kaspi.kz",
            country_codes: ["KZ"],
          },
          {
            schema_version: 1,
            name: "Global Pay",
            canonical_domain: "global.example",
            primary_url: "https://global.example",
            country_codes: [],
          },
        ]}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Filters & sorting" }));
    expect(screen.getAllByRole("checkbox", { name: "Not specified" })).toHaveLength(2);
    expect(screen.getByRole("checkbox", { name: "Kaspi" })).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Kazakhstan" }));
    expect(screen.getByRole("checkbox", { name: "Kaspi" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Global Pay" })).toBeNull();
  });

  it("preselects a legacy singleton country and service in the linked controls", async () => {
    const user = userEvent.setup();
    render(
      <CatalogFilters
        query={query({ countryCode: "KZ", serviceDomain: "kaspi.kz" })}
        labels={{
          ...labels,
          unspecifiedOption: "Not specified",
          refineButton: "Filters & sorting",
        }}
        services={[
          {
            schema_version: 1,
            name: "Kaspi",
            canonical_domain: "kaspi.kz",
            primary_url: "https://kaspi.kz",
            country_codes: ["KZ"],
          },
        ]}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Filters & sorting (2)" }));
    expect(screen.getByRole("checkbox", { name: "Kazakhstan" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Kaspi" })).toBeChecked();
  });

  it("renders an accessible updated date range with a clear control", async () => {
    const user = userEvent.setup();
    render(
      <CatalogFilters
        query={query({ updatedFrom: "2026-01-01", updatedTo: "2026-01-31" })}
        labels={{
          ...labels,
          updatedFrom: "Updated from",
          updatedTo: "Updated to",
          clearUpdatedRange: "Clear dates",
        }}
      />,
    );
    expect(screen.getByRole("link", { name: /Updated from: 2026-01-01/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Updated to: 2026-01-31/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Filters/ }));
    expect(screen.getByLabelText("Updated from")).toHaveValue("2026-01-01");
    expect(screen.getByLabelText("Updated to")).toHaveValue("2026-01-31");
    await user.click(screen.getByRole("button", { name: "Clear dates" }));
    expect(screen.getByLabelText("Updated from")).toHaveValue("");
    expect(screen.getByLabelText("Updated to")).toHaveValue("");
  });

  it("adapts legacy singleton harness and type filters into checked multiselect values", async () => {
    const user = userEvent.setup();
    render(
      <CatalogFilters
        query={query({
          resource: "components",
          harnessId: "codex",
          componentType: "skill",
          authors: ["alice"],
          verifiedOnly: true,
          sort: "likes",
          supportTier: "primary",
          supportState: "verified",
        })}
        labels={labels}
      />,
    );
    await user.click(screen.getByRole("button", { name: /^Filters/ }));
    expect(screen.getByRole("checkbox", { name: "codex" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "skill" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Only verified/ })).toBeChecked();
    expect(screen.getByRole("searchbox", { name: /Author/ })).toHaveValue("alice");
    expect(screen.queryByRole("combobox", { name: "Support tier" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Support state" })).toBeNull();
  });

  it("uses an overlay filter surface on a narrow viewport without dropping controls", async () => {
    const user = userEvent.setup();
    render(<CatalogFilters query={query()} labels={labels} />);
    const open = screen.getByRole("button", { name: "Filters" });
    await user.click(open);
    const surface = await screen.findByRole("dialog", { name: "Filters" });
    expect(surface).toHaveAttribute("id", "catalog-refine");
    expect(surface).toHaveAttribute("data-filter-surface", "drawer");
    expect(surface).toHaveClass(
      "fixed",
      "inset-x-0",
      "bottom-0",
      "overflow-x-hidden",
      "overflow-y-auto",
    );
    expect(surface).toContainElement(document.activeElement as HTMLElement);
    expect(within(surface).getByRole("button", { name: "Close" })).toBeInTheDocument();
    expect(within(surface).getByRole("combobox", { name: "Catalog resource" })).toBeInTheDocument();
    expect(within(surface).getByRole("group", { name: /Tag/ })).toBeInTheDocument();
    expect(within(surface).getByRole("group", { name: "Harness" })).toBeInTheDocument();
    expect(within(surface).getByRole("searchbox", { name: /Author/ })).toBeInTheDocument();
    expect(within(surface).getByRole("button", { name: "Apply filters" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sort results" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Result layout" })).toBeInTheDocument();
    const close = within(surface).getByRole("button", { name: "Close" });
    const apply = within(surface).getByRole("button", { name: "Apply filters" });
    expect(close).toHaveFocus();
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(apply).toHaveFocus();
    await user.keyboard("{Tab}");
    expect(close).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(document.getElementById("catalog-refine")).toBeNull();
    expect(open).toHaveFocus();
    await user.click(open);
    const backdrop = screen.getAllByRole("button", { name: "Close" })[0] as HTMLElement;
    expect(backdrop).toHaveClass("fixed", "inset-0");
    await user.click(backdrop);
    expect(document.getElementById("catalog-refine")).toBeNull();
    expect(open).toHaveFocus();
  });

  it("labels date chips and updates the date range from the filter panel", async () => {
    const user = userEvent.setup();
    const labelsWithoutBoth = Object.fromEntries(
      Object.entries(labels).filter(([key]) => key !== "resourceBoth"),
    ) as Omit<typeof labels, "resourceBoth">;
    render(
      <CatalogFilters
        query={query({ updatedFrom: "2026-01-01", updatedTo: "2026-01-31" })}
        labels={{
          ...labelsWithoutBoth,
          updatingLabel: "Updating catalog",
        }}
      />,
    );
    expect(screen.getByRole("link", { name: /Updated from: 2026-01-01/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Updated to: 2026-01-31/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Filters/ }));
    expect(screen.getByRole("option", { name: "Both" })).toBeInTheDocument();
    const from = screen.getByLabelText("Updated from");
    await user.clear(from);
    await user.type(from, "2026-02-01");
    expect(from).toHaveValue("2026-02-01");
    const to = screen.getByLabelText("Updated to");
    await user.clear(to);
    await user.type(to, "2026-02-28");
    expect(to).toHaveValue("2026-02-28");
  });

  it("keeps services without a country when unspecified is selected", async () => {
    const user = userEvent.setup();
    render(
      <CatalogFilters
        query={query()}
        labels={{
          ...labels,
          unspecifiedOption: "Not specified",
          refineButton: "Filters & sorting",
        }}
        services={[
          {
            schema_version: 1,
            name: "Kaspi",
            canonical_domain: "kaspi.kz",
            primary_url: "https://kaspi.kz",
            country_codes: ["KZ"],
          },
          {
            schema_version: 1,
            name: "Global Pay",
            canonical_domain: "global.example",
            primary_url: "https://global.example",
            country_codes: [],
          },
        ]}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Filters & sorting" }));
    const unspecified = screen.getAllByRole("checkbox", { name: "Not specified" })[0];
    if (!unspecified) {
      throw new Error("expected unspecified country checkbox");
    }
    await user.click(unspecified);
    expect(screen.getByRole("checkbox", { name: "Global Pay" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Kaspi" })).toBeNull();
  });

  it("gives each filter a distinct localized help string", async () => {
    const user = userEvent.setup();
    render(<CatalogFilters query={query({ resource: "components" })} labels={labels} />);
    await user.click(screen.getByRole("button", { name: "Filters" }));
    const texts = [...document.querySelectorAll('[role="tooltip"]')].map((node) =>
      node.textContent.trim(),
    );
    expect(texts.length).toBeGreaterThanOrEqual(8);
    expect(new Set(texts).size).toBe(texts.length);
    expect(texts).toEqual(
      expect.arrayContaining([
        "Help for tags",
        "Help for harnesses",
        "Help for component types",
        "Help for authors",
        "Help for verified only",
        "Help for countries",
        "Help for services",
        "Help for update dates",
      ]),
    );
    expect(texts.every((text) => text !== labels.filterHelpBody)).toBe(true);
  });

  it("falls back to the shared help copy when optional facet help is absent", async () => {
    const user = userEvent.setup();
    const fallbackLabels = { ...labels };
    delete (fallbackLabels as Partial<typeof labels>).tagFilterHelp;
    delete (fallbackLabels as Partial<typeof labels>).harnessFilterHelp;
    delete (fallbackLabels as Partial<typeof labels>).typeFilterHelp;
    delete (fallbackLabels as Partial<typeof labels>).authorFilterHelp;
    delete (fallbackLabels as Partial<typeof labels>).verifiedOnlyHelp;
    delete (fallbackLabels as Partial<typeof labels>).countryFilterHelp;
    delete (fallbackLabels as Partial<typeof labels>).serviceFilterHelp;
    delete (fallbackLabels as Partial<typeof labels>).updatedRangeHelp;

    render(<CatalogFilters query={query({ resource: "components" })} labels={fallbackLabels} />);
    await user.click(screen.getByRole("button", { name: "Filters" }));
    expect(screen.getAllByText("Filter help").length).toBeGreaterThanOrEqual(7);
  });
});
