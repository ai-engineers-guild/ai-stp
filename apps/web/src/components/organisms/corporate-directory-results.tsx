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
import { useRouter } from "@/lib/i18n/navigation";

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

function directoryLabels(t: (key: string) => string) {
  return {
    lead: t("lead"),
    ownerTeam: t("owner"),
    teams: t("teams"),
    projects: t("projects"),
    technologies: t("technologies"),
    team: t("team"),
    employee: t("employee"),
    author: t("author"),
    owner: t("owner"),
    type: t("type"),
    moreActions: t("moreActions"),
    unknownEmployee: t("unknownEmployee"),
    notAvailable: t("notAvailable"),
  };
}

export function CorporateDirectoryResults({
  resource,
  items,
  filters = "",
  initialQuery = "",
  addLabel,
  cancelLabel,
  adding = false,
  onAdd,
  catalogFacets = EMPTY_CATALOG_FACETS,
  initialCatalogSelected = EMPTY_CATALOG_SELECTION,
}: {
  resource: DirectoryResource;
  items: readonly DirectoryItem[];
  filters?: string;
  initialQuery?: string;
  addLabel?: string | undefined;
  cancelLabel?: string | undefined;
  adding?: boolean | undefined;
  onAdd?: (() => void) | undefined;
  catalogFacets?: readonly CorporateCatalogFacetConfig[];
  initialCatalogSelected?: Partial<Record<CorporateCatalogFacet, string[]>>;
}) {
  const t = useTranslations("hub");
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
    window.history.replaceState(window.history.state, "", url);
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

  function applyCatalogFacets(values: Partial<Record<CorporateCatalogFacet, string[]>>) {
    const url = new URL(window.location.href);
    for (const facet of catalogFacets) {
      url.searchParams.delete(facet.key);
      for (const value of values[facet.key] ?? []) url.searchParams.append(facet.key, value);
    }
    setCatalogSelected(values);
    setReturnFilters(url.searchParams.toString());
    router.push(`${url.pathname}${url.search ? url.search : ""}`);
  }

  const visible = sortItems(
    items.filter(
      (item) =>
        (!query || item.name.toLocaleLowerCase().includes(query.toLocaleLowerCase())) &&
        matchesDirectoryFilters(item, selected) &&
        (!leadOnly || item.is_lead),
    ),
    sort,
  );
  const labels = directoryLabels(t);

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
      />
      <div className="flex items-center justify-end gap-3">
        <p className="text-muted-foreground text-sm" aria-live="polite">
          {visible.length} {t(resource === "members" ? "employees" : resource)}
        </p>
      </div>
      {visible.length ? (
        <ul
          className={view === "cards" ? "grid min-w-0 gap-4 md:grid-cols-2" : "grid min-w-0 gap-3"}
        >
          {visible.map((item) => (
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
      ) : (
        <p className="text-muted-foreground border-border rounded-lg border border-dashed p-8 text-center text-sm">
          {t(items.length ? "noMatches" : "empty")}
        </p>
      )}
    </section>
  );
}
