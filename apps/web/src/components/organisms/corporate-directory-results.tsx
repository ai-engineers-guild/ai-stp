"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { CorporateDirectoryCard } from "@/components/organisms/corporate-directory-card";
import {
  CorporateDirectoryToolbar,
  type CorporateDirectorySelectedFilters,
} from "@/components/organisms/corporate-directory-toolbar";
import {
  directoryFacetParams,
  directoryFacets,
  directoryReferences,
  type DirectoryFacet,
  type DirectoryItem,
  type DirectoryResource,
  type CorporateCatalogFacet,
  type CorporateCatalogFacetConfig,
} from "./corporate-directory-types";
import { usePathname, useRouter } from "@/lib/i18n/navigation";
import { PageNav } from "@/components/organisms/catalog-page-nav";
import type { CorporateDirectoryFacets } from "@/lib/api/generated/types.gen";

export type { DirectoryItem, DirectoryResource } from "./corporate-directory-types";

const EMPTY_CATALOG_FACETS: readonly CorporateCatalogFacetConfig[] = [];
const EMPTY_CATALOG_SELECTION: Partial<Record<CorporateCatalogFacet, string[]>> = {};

export function matchesDirectoryFilters(
  item: DirectoryItem,
  selected: Partial<Record<DirectoryFacet, string[]>>,
) {
  return Object.entries(selected).every(
    ([facet, values]) =>
      !values.length ||
      directoryReferences(item, facet as DirectoryFacet).some((ref) => values.includes(ref.id)),
  );
}

function currentReturnFilters(seed: string): string {
  const current = new URLSearchParams(window.location.search);
  const initial = new URLSearchParams(seed);
  for (const [key, value] of initial) {
    if (!current.has(key)) current.append(key, value);
  }
  current.delete("status");
  current.delete("state");
  return current.toString();
}

function restoreFilters(seed: string, resource: DirectoryResource) {
  const params = new URLSearchParams(window.location.search);
  const initial = new URLSearchParams(seed);
  const defaultView: "list" | "cards" = resource === "technologies" ? "list" : "cards";
  return {
    query: params.get("query") ?? initial.get("query") ?? "",
    view:
      params.get("view") === "list"
        ? ("list" as const)
        : params.get("view") === "cards"
          ? ("cards" as const)
          : defaultView,
    sort: params.get("sort") === "name_desc" ? ("name_desc" as const) : ("name" as const),
    leadOnly: params.get("is_lead") === "true",
    selected: Object.fromEntries(
      directoryFacets[resource].map((facet) => [facet, params.getAll(directoryFacetParams[facet])]),
    ) as CorporateDirectorySelectedFilters,
  };
}

function sortItems(items: readonly DirectoryItem[], sort: "name" | "name_desc") {
  return [...items].sort((left, right) =>
    sort === "name_desc"
      ? right.name.localeCompare(left.name)
      : left.name.localeCompare(right.name),
  );
}

function cardItem(item: DirectoryItem, resource: DirectoryResource): DirectoryItem {
  if (resource === "components") return item;
  const withoutDescription = { ...item };
  delete withoutDescription.description;
  return withoutDescription;
}

function restoreCatalogSelection(
  catalogFacets: readonly CorporateCatalogFacetConfig[],
  initialCatalogSelected: Partial<Record<CorporateCatalogFacet, string[]>>,
) {
  const search = window.location.search ? new URLSearchParams(window.location.search) : null;
  return Object.fromEntries(
    catalogFacets.map((facet) => [
      facet.key,
      search ? search.getAll(facet.key) : (initialCatalogSelected[facet.key] ?? []),
    ]),
  ) as Partial<Record<CorporateCatalogFacet, string[]>>;
}

function directoryLabels(
  t: (key: string) => string,
  editPresentation: string,
  share: string,
  report: string,
) {
  return {
    lead: t("lead"),
    ownerTeam: t("owner"),
    operationalOwner: t("operationalOwner"),
    teams: t("teams"),
    projects: t("projects"),
    technologies: t("technologies"),
    categories: t("categories"),
    team: t("team"),
    employee: t("employee"),
    author: t("author"),
    owner: t("owner"),
    type: t("type"),
    moreActions: t("moreActions"),
    openDetails: t("openDetails"),
    edit: t("edit"),
    editPresentation,
    copyId: t("copyId"),
    share,
    report,
    unknownEmployee: t("unknownEmployee"),
    notAvailable: t("notAvailable"),
  };
}

function DirectoryItemList({
  resource,
  items,
  labels,
  returnFilters,
  view,
  emptyLabel,
}: {
  resource: DirectoryResource;
  items: readonly DirectoryItem[];
  labels: ReturnType<typeof directoryLabels>;
  returnFilters: string;
  view: "list" | "cards";
  emptyLabel: string;
}) {
  if (!items.length) {
    return (
      <p className="text-muted-foreground border-border rounded-lg border border-dashed p-8 text-center text-sm">
        {emptyLabel}
      </p>
    );
  }
  return (
    <ul className={view === "cards" ? "grid min-w-0 gap-4 md:grid-cols-2" : "grid min-w-0 gap-3"}>
      {items.map((item) => (
        <CorporateDirectoryCard
          key={item.id}
          resource={resource}
          item={cardItem(item, resource)}
          labels={labels}
          returnFilters={returnFilters}
          view={view}
        />
      ))}
    </ul>
  );
}

function DirectoryPagination({
  filters,
  label,
  pageNumber,
  pageSize,
  total,
}: {
  filters: string;
  label: string;
  pageNumber: number;
  pageSize: number;
  total: number;
}) {
  if (total <= pageSize) return null;
  return (
    <PageNav
      label={label}
      pageNumber={pageNumber}
      totalPages={Math.ceil(total / pageSize)}
      hrefFor={(page) => {
        const params = new URLSearchParams(filters);
        params.set("page", String(page));
        return `?${params.toString()}`;
      }}
    />
  );
}

function DirectoryPageSize({
  pageSize,
  onChange,
  label,
}: {
  pageSize: number;
  onChange: (value: number) => void;
  label: string;
}) {
  return (
    <label className="text-muted-foreground flex items-center gap-2 text-sm">
      <span>{label}</span>
      <select
        value={pageSize}
        onChange={(event) => {
          onChange(Number(event.target.value));
        }}
        className="border-input bg-background text-foreground h-9 rounded-sm border px-2 text-sm"
      >
        {[10, 24, 48, 64].map((size) => (
          <option key={size} value={size}>
            {size}
          </option>
        ))}
      </select>
    </label>
  );
}

function visibleDirectoryItems(
  items: readonly DirectoryItem[],
  query: string,
  selected: CorporateDirectorySelectedFilters,
  leadOnly: boolean,
  sort: "name" | "name_desc",
) {
  return sortItems(
    items.filter(
      (item) =>
        (!query || item.name.toLocaleLowerCase().includes(query.toLocaleLowerCase())) &&
        matchesDirectoryFilters(item, selected) &&
        (!leadOnly || item.is_lead),
    ),
    sort,
  );
}

type CorporateDirectoryResultsProps = {
  resource: DirectoryResource;
  items: readonly DirectoryItem[];
  filters?: string;
  initialQuery?: string;
  addLabel?: string | undefined;
  cancelLabel?: string | undefined;
  adding?: boolean | undefined;
  onAdd?: (() => void) | undefined;
  addHref?: string | undefined;
  catalogFacets?: readonly CorporateCatalogFacetConfig[];
  initialCatalogSelected?: Partial<Record<CorporateCatalogFacet, string[]>>;
  serverPaginated?: boolean;
  pageNumber?: number;
  pageSize?: number;
  total?: number | undefined;
  paginationLabel?: string | undefined;
  facets?: CorporateDirectoryFacets;
};

export function CorporateDirectoryResults({
  resource,
  items,
  filters = "",
  initialQuery = "",
  addLabel,
  cancelLabel,
  adding = false,
  onAdd,
  addHref,
  catalogFacets = EMPTY_CATALOG_FACETS,
  initialCatalogSelected = EMPTY_CATALOG_SELECTION,
  serverPaginated = false,
  pageNumber = 1,
  pageSize = 24,
  total,
  paginationLabel = "Pagination",
  facets,
}: CorporateDirectoryResultsProps) {
  const t = useTranslations("hub");
  const objects = useTranslations("objects");
  const [query, setQuery] = useState(initialQuery);
  const [view, setView] = useState<"list" | "cards">(
    resource === "technologies" ? "list" : "cards",
  );
  const [sort, setSort] = useState<"name" | "name_desc">("name");
  const [selected, setSelected] = useState<CorporateDirectorySelectedFilters>({});
  const [leadOnly, setLeadOnly] = useState(false);
  const [returnFilters, setReturnFilters] = useState(filters);
  const [catalogSelected, setCatalogSelected] = useState(initialCatalogSelected);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    function restore() {
      const next = restoreFilters(filters, resource);
      setQuery(next.query);
      setView(next.view);
      setSort(next.sort);
      setLeadOnly(next.leadOnly);
      setSelected(next.selected);
      setReturnFilters(currentReturnFilters(filters));
      setCatalogSelected(restoreCatalogSelection(catalogFacets, initialCatalogSelected));
    }
    restore();
    window.addEventListener("popstate", restore);
    return () => {
      window.removeEventListener("popstate", restore);
    };
  }, [catalogFacets, filters, initialCatalogSelected, resource]);

  function persist(name: string, values: string[]) {
    const url = new URL(window.location.href);
    url.searchParams.delete("status");
    url.searchParams.delete("state");
    url.searchParams.delete(name);
    values.forEach((value) => {
      url.searchParams.append(name, value);
    });
    if (serverPaginated && name !== "view") {
      url.searchParams.set("page", "1");
      router.push(`${pathname}${url.search}`);
    } else {
      window.history.replaceState(window.history.state, "", url);
    }
    setReturnFilters(url.searchParams.toString());
  }

  function changeQuery(value: string) {
    setQuery(value);
    persist("query", value ? [value] : []);
  }

  function changeFacet(facet: DirectoryFacet, values: string[]) {
    setSelected((previous) => ({ ...previous, [facet]: values }));
    persist(directoryFacetParams[facet], values);
  }

  function changeView(value: "list" | "cards") {
    setView(value);
    persist("view", [value]);
  }

  function changeSort(value: "name" | "name_desc") {
    setSort(value);
    persist("sort", [value]);
  }

  function changeLeadOnly(value: boolean) {
    setLeadOnly(value);
    persist("is_lead", value ? ["true"] : []);
  }

  function changePageSize(value: number) {
    const url = new URL(window.location.href);
    url.searchParams.set("page_size", String(value));
    url.searchParams.set("page", "1");
    setReturnFilters(url.searchParams.toString());
    if (serverPaginated) router.push(`${pathname}${url.search}`);
  }

  function applyCatalogFacets(values: Partial<Record<CorporateCatalogFacet, string[]>>) {
    const url = new URL(window.location.href);
    url.searchParams.set("page", "1");
    for (const facet of catalogFacets) {
      url.searchParams.delete(facet.key);
      for (const value of values[facet.key] ?? []) url.searchParams.append(facet.key, value);
    }
    setCatalogSelected(values);
    setReturnFilters(url.searchParams.toString());
    router.push(`${pathname}${url.search ? url.search : ""}`);
  }

  const visible = visibleDirectoryItems(items, query, selected, leadOnly, sort);
  return (
    <section className="min-w-0 space-y-5">
      <CorporateDirectoryToolbar
        resource={resource}
        items={items}
        query={query}
        selected={selected}
        leadOnly={leadOnly}
        view={view}
        sort={sort}
        onQueryChange={changeQuery}
        onFacetChange={changeFacet}
        onLeadOnlyChange={changeLeadOnly}
        onViewChange={changeView}
        onSortChange={changeSort}
        catalogFacets={catalogFacets}
        catalogSelected={catalogSelected}
        onCatalogApply={applyCatalogFacets}
        addLabel={addLabel}
        cancelLabel={cancelLabel}
        adding={adding}
        onAdd={onAdd}
        addHref={addHref}
        {...(facets ? { facets } : {})}
      />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-muted-foreground text-sm" aria-live="polite">
          {serverPaginated ? (total ?? visible.length) : visible.length}{" "}
          {t(resource === "members" ? "employees" : resource)}
        </p>
        {serverPaginated ? (
          <DirectoryPageSize pageSize={pageSize} onChange={changePageSize} label={t("pageSize")} />
        ) : null}
      </div>
      <DirectoryItemList
        resource={resource}
        items={visible}
        labels={directoryLabels(t, objects("editPresentation"), t("share"), t("report"))}
        returnFilters={returnFilters}
        view={view}
        emptyLabel={t(items.length ? "noMatches" : "empty")}
      />
      {serverPaginated && total ? (
        <DirectoryPagination
          filters={filters}
          label={paginationLabel}
          pageNumber={pageNumber}
          pageSize={pageSize}
          total={total}
        />
      ) : null}
    </section>
  );
}
