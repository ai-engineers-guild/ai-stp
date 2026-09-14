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
} from "./corporate-directory-types";

export type { DirectoryItem, DirectoryResource } from "./corporate-directory-types";

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
  return current.toString();
}

function restoreFilters(seed: string, resource: DirectoryResource) {
  const params = new URLSearchParams(window.location.search);
  const initial = new URLSearchParams(seed);
  return {
    query: params.get("query") ?? initial.get("query") ?? "",
    status: params.get("status") ?? initial.get("status") ?? "",
    view: params.get("view") === "cards" ? ("cards" as const) : ("list" as const),
    sort: params.get("sort") === "state" ? ("state" as const) : ("name" as const),
    leadOnly: params.get("is_lead") === "true",
    selected: Object.fromEntries(
      directoryFacets[resource].map((facet) => [facet, params.getAll(directoryFacetParams[facet])]),
    ) as CorporateDirectorySelectedFilters,
  };
}

function sortItems(items: readonly DirectoryItem[], sort: "name" | "state") {
  return [...items].sort((left, right) =>
    sort === "state"
      ? left.state.localeCompare(right.state) || left.name.localeCompare(right.name)
      : left.name.localeCompare(right.name),
  );
}

export function CorporateDirectoryResults({
  resource,
  items,
  filters = "",
  initialQuery = "",
  initialStatus = "",
}: {
  resource: DirectoryResource;
  items: readonly DirectoryItem[];
  filters?: string;
  initialQuery?: string;
  initialStatus?: string;
}) {
  const t = useTranslations("hub");
  const [query, setQuery] = useState(initialQuery);
  const [status, setStatus] = useState(initialStatus);
  const [view, setView] = useState<"list" | "cards">("list");
  const [sort, setSort] = useState<"name" | "state">("name");
  const [selected, setSelected] = useState<CorporateDirectorySelectedFilters>({});
  const [leadOnly, setLeadOnly] = useState(false);
  const [returnFilters, setReturnFilters] = useState(filters);

  useEffect(() => {
    function restore() {
      const next = restoreFilters(filters, resource);
      setQuery(next.query);
      setStatus(next.status);
      setView(next.view);
      setSort(next.sort);
      setLeadOnly(next.leadOnly);
      setSelected(next.selected);
      setReturnFilters(currentReturnFilters(filters));
    }
    restore();
    window.addEventListener("popstate", restore);
    return () => {
      window.removeEventListener("popstate", restore);
    };
  }, [filters, resource]);

  function persist(name: string, values: string[]) {
    const url = new URL(window.location.href);
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

  function changeStatus(value: string) {
    setStatus(value);
    persist("status", value ? [value] : []);
  }

  function changeFacet(facet: DirectoryFacet, values: string[]) {
    setSelected((previous) => ({ ...previous, [facet]: values }));
    persist(directoryFacetParams[facet], values);
  }

  function changeView(value: "list" | "cards") {
    setView(value);
    persist("view", [value]);
  }

  function changeSort(value: "name" | "state") {
    setSort(value);
    persist("sort", [value]);
  }

  function changeLeadOnly(value: boolean) {
    setLeadOnly(value);
    persist("is_lead", value ? ["true"] : []);
  }

  const visible = sortItems(
    items.filter(
      (item) =>
        (!query ||
          `${item.name} ${item.description ?? ""}`
            .toLocaleLowerCase()
            .includes(query.toLocaleLowerCase())) &&
        (!status || item.state === status) &&
        matchesDirectoryFilters(item, selected) &&
        (!leadOnly || item.is_lead),
    ),
    sort,
  );
  const labels = {
    active: t("active"),
    draft: t("draft"),
    archived: t("archived"),
    deprecated: t("deprecated"),
    suspended: t("suspended"),
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

  return (
    <section className="min-w-0 space-y-5">
      <CorporateDirectoryToolbar
        resource={resource}
        items={items}
        query={query}
        status={status}
        selected={selected}
        leadOnly={leadOnly}
        view={view}
        sort={sort}
        onQueryChange={changeQuery}
        onStatusChange={changeStatus}
        onFacetChange={changeFacet}
        onLeadOnlyChange={changeLeadOnly}
        onViewChange={changeView}
        onSortChange={changeSort}
      />
      <div className="flex items-center justify-between gap-3">
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
              item={item}
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
