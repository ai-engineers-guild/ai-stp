"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { Button } from "@/components/atoms/button";
import { CatalogQueryField } from "@/components/molecules/catalog-query-field";
import { CatalogChoiceMenu } from "@/components/molecules/catalog-choice-menu";
import {
  CatalogFilterPanel,
  type CatalogFilterPanelLabels,
} from "@/components/organisms/catalog-filter-panel";
import { CatalogSearchForm } from "@/components/organisms/catalog-search-form";
import type { ExternalProduct } from "@/lib/api/catalog";
import {
  appliedFilterChips,
  catalogQueryToRecord,
  countAppliedFilters,
  type CatalogResource,
  type ParsedCatalogQuery,
} from "@/lib/catalog-query";
import { defaultCatalogQuery } from "@/lib/catalog-query-defaults";
import { cn } from "@/lib/cn";
import { Link } from "@/lib/i18n/navigation";
import { UI } from "@/lib/ui-selectors";
import { Icon } from "@/theme";

type CatalogFiltersProps = {
  query: ParsedCatalogQuery;
  locale?: string;
  services?: ExternalProduct[];
  intro?: string;
  labels: CatalogFilterPanelLabels & {
    search: string;
    searchPlaceholder: string;
    searchHelp: string;
    resetAll: string;
    dismissFilter: string;
    sortBy: string;
    sortDirection: string;
    sortRelevance: string;
    sortUpdated: string;
    sortLikes: string;
    sortAscending: string;
    sortDescending: string;
    viewLabel: string;
    cardsView: string;
    listView: string;
    refineButton?: string;
    queryCorrection?: string;
    updatingLabel?: string;
    updatedFrom?: string;
    updatedTo?: string;
    clearUpdatedRange?: string;
    resourceBoth?: string;
  };
};

const FILTER_QUERY_KEYS = new Set([
  "tags",
  "harness_id",
  "harness_ids",
  "component_type",
  "component_types",
  "authors",
  "verified_only",
  "include_experimental",
  "sort",
  "sort_direction",
  "view",
  "support_tier",
  "support_state",
  "service_domain",
  "service_domains",
  "country_code",
  "country_codes",
  "updated_from",
  "updated_to",
]);

function hrefFor(query: ParsedCatalogQuery) {
  return `/catalog?${new URLSearchParams(catalogQueryToRecord(query)).toString()}`;
}

export function CatalogFilters({
  query,
  labels,
  services = [],
  intro = "",
  locale = "en",
}: CatalogFiltersProps) {
  const [searchOpen, setSearchOpen] = useState(Boolean(query.q));
  const [filtersOpen, setFiltersOpen] = useState(false);
  const appliedCount = countAppliedFilters(query);
  const chips = appliedFilterChips(query);
  const resetHref = hrefFor(defaultCatalogQuery(query.resource));
  const hiddenOmit = new Set(["page", "page_size", "resource"]);
  if (searchOpen) hiddenOmit.add("q");
  if (filtersOpen) {
    for (const key of FILTER_QUERY_KEYS) hiddenOmit.add(key);
  }

  return (
    <CatalogSearchForm
      id="catalog-search-form"
      className="w-full"
      {...(labels.updatingLabel ? { updatingLabel: labels.updatingLabel } : {})}
    >
      <input type="hidden" name="page_size" value={String(query.pageSize)} />
      {Object.entries(catalogQueryToRecord(query))
        .filter(([key]) => !hiddenOmit.has(key))
        .map(([key, value]) => (
          <input key={key} type="hidden" name={key} value={value} />
        ))}
      {!filtersOpen ? <input type="hidden" name="resource" value={query.resource} /> : null}
      <div className="grid min-w-0 items-start gap-4 md:grid-cols-[minmax(0,1fr)_auto]">
        <p className="text-muted-foreground max-w-3xl min-w-0 text-sm leading-relaxed">{intro}</p>
        <div className="flex min-w-0 flex-wrap items-center gap-2 md:justify-end">
          <DisclosureButton
            open={searchOpen}
            controls="catalog-text-search"
            ui={UI.catalog.search}
            label={labels.search}
            onToggle={() => {
              setSearchOpen((value) => !value);
            }}
          >
            <Icon name="search" size="sm" />
          </DisclosureButton>
          <DisclosureButton
            open={filtersOpen}
            controls="catalog-refine"
            ui={UI.catalog.filters}
            label={`${labels.refineButton ?? labels.filtersButton}${appliedCount ? ` (${appliedCount})` : ""}`}
            onToggle={() => {
              setFiltersOpen((value) => !value);
            }}
          >
            <Icon name="controls" size="sm" />
          </DisclosureButton>
          <CatalogDisplayControls query={query} labels={labels} />
        </div>
      </div>

      <div className="relative mt-4 min-w-0 space-y-3">
        {searchOpen ? (
          <section
            id="catalog-text-search"
            className="border-border bg-card min-w-0 overflow-x-hidden rounded-lg border p-4 sm:p-5"
          >
            <CatalogQueryField
              label={labels.search}
              placeholder={labels.searchPlaceholder}
              submitLabel={labels.search}
              defaultValue={query.q}
              correctionLabel={labels.queryCorrection ?? "Did you mean"}
            />
            <p className="text-muted-foreground mt-2 max-w-3xl text-xs leading-relaxed">
              {labels.searchHelp}
            </p>
          </section>
        ) : null}
        {filtersOpen ? (
          <RefineSurface
            labels={labels}
            onClose={() => {
              setFiltersOpen(false);
            }}
          >
            <div className="mb-5 max-w-xs">
              <ResourceSwitch query={query} labels={labels} />
            </div>
            <CatalogFilterPanel query={query} labels={labels} services={services} locale={locale} />
            <div className="border-border bg-card sticky bottom-0 mt-6 flex flex-wrap items-center justify-between gap-3 border-t py-5">
              <Link
                href={resetHref}
                prefetch={false}
                className="text-muted-foreground inline-flex min-h-11 items-center text-sm underline underline-offset-4"
              >
                {labels.resetAll}
              </Link>
              <Button type="submit" className="min-h-11 w-full sm:w-auto">
                <Icon name="filter" size="sm" />
                {labels.applyFilters}
              </Button>
            </div>
          </RefineSurface>
        ) : null}
      </div>

      {chips.length ? (
        <div className="mt-3 flex min-w-0 flex-wrap gap-2" aria-label={labels.filtersButton}>
          {chips.map((chip) => (
            <Link
              key={chip.key}
              href={hrefFor(chip.without)}
              prefetch={false}
              className="border-border bg-muted inline-flex min-h-11 max-w-full items-center rounded-md border px-3 py-1 font-mono text-xs break-all"
            >
              {chipLabel(chip.key, chip.label, labels)} ×
            </Link>
          ))}
        </div>
      ) : null}
    </CatalogSearchForm>
  );
}

function CatalogDisplayControls({
  query,
  labels,
}: {
  query: ParsedCatalogQuery;
  labels: CatalogFiltersProps["labels"];
}) {
  return (
    <>
      <CatalogChoiceMenu
        label={labels.viewLabel}
        icon={query.view === "cards" ? "cards" : "list"}
        options={[
          {
            label: labels.listView,
            href: hrefFor({ ...query, view: "list", pageNumber: 1 }),
            active: query.view === "list",
            icon: "list",
          },
          {
            label: labels.cardsView,
            href: hrefFor({ ...query, view: "cards", pageNumber: 1 }),
            active: query.view === "cards",
            icon: "cards",
          },
        ]}
      />
      <CatalogChoiceMenu
        label={labels.sortBy}
        icon="sort"
        align="end"
        options={[
          {
            label: labels.sortRelevance,
            href: hrefFor({ ...query, sort: "relevance", pageNumber: 1 }),
            active: query.sort === "relevance",
          },
          {
            label: labels.sortUpdated,
            href: hrefFor({ ...query, sort: "updated_at", pageNumber: 1 }),
            active: query.sort === "updated_at",
          },
          {
            label: labels.sortLikes,
            href: hrefFor({ ...query, sort: "likes", pageNumber: 1 }),
            active: query.sort === "likes",
          },
          {
            label: labels.sortAscending,
            href: hrefFor({ ...query, sortDirection: "asc", pageNumber: 1 }),
            active: query.sortDirection === "asc",
            separatorBefore: true,
          },
          {
            label: labels.sortDescending,
            href: hrefFor({ ...query, sortDirection: "desc", pageNumber: 1 }),
            active: query.sortDirection === "desc",
          },
        ]}
      />
    </>
  );
}

const REFINE_FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

function refineFocusables(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(REFINE_FOCUSABLE)].filter(
    (el) => el.getAttribute("aria-hidden") !== "true" && el.tabIndex !== -1,
  );
}

function RefineSurface({
  labels,
  onClose,
  children,
}: {
  labels: CatalogFiltersProps["labels"];
  onClose: () => void;
  children: ReactNode;
}) {
  const title = labels.refineButton ?? labels.filtersButton;
  const surfaceRef = useRef<HTMLElement>(null);
  // Assigned after commit, not during render. A render React throws away
  // would otherwise leave this pointing at a handler that never took effect.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    const surface = surfaceRef.current;
    if (!surface) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const first = refineFocusables(surface)[0];
    (first ?? surface).focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = refineFocusables(surface);
      if (items.length === 0) return;
      const start = items[0];
      const end = items[items.length - 1];
      if (!start || !end) return;
      if (event.shiftKey && document.activeElement === start) {
        event.preventDefault();
        end.focus();
      } else if (!event.shiftKey && document.activeElement === end) {
        event.preventDefault();
        start.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", onKeyDown);
      previous?.focus();
    };
  }, []);

  return (
    <>
      <button
        type="button"
        className="bg-foreground/40 fixed inset-0 z-[60]"
        aria-label={labels.closeFilters}
        tabIndex={-1}
        onClick={onClose}
      />
      <section
        ref={surfaceRef}
        id="catalog-refine"
        role="dialog"
        aria-modal="true"
        aria-labelledby="catalog-refine-title"
        tabIndex={-1}
        data-filter-surface="drawer"
        className={cn(
          "border-border bg-card fixed z-[70] overflow-x-hidden overflow-y-auto border shadow-md",
          "inset-x-0 bottom-0 max-h-[min(92dvh,calc(100vh-1rem))] w-full rounded-t-lg px-4",
          "pb-[max(1.25rem,env(safe-area-inset-bottom))]",
          "md:inset-auto md:top-1/2 md:left-1/2 md:max-h-[calc(100vh-2rem)] md:w-[calc(100vw-2rem)]",
          "md:max-w-3xl md:-translate-x-1/2 md:-translate-y-1/2 md:rounded-lg md:px-6",
        )}
      >
        <div className="border-border bg-card sticky top-0 z-10 mb-5 flex min-w-0 items-center justify-between gap-3 border-b py-4 sm:py-5">
          <h2 id="catalog-refine-title" className="min-w-0 text-lg font-medium break-words">
            {title}
          </h2>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-11 w-11 shrink-0"
            aria-label={labels.closeFilters}
            onClick={onClose}
          >
            <Icon name="close" size="sm" />
          </Button>
        </div>
        {children}
      </section>
    </>
  );
}

function chipLabel(key: string, label: string, labels: CatalogFiltersProps["labels"]): string {
  if (key === "updated_from") return `${labels.updatedFrom ?? "Updated from"}: ${label}`;
  if (key === "updated_to") return `${labels.updatedTo ?? "Updated to"}: ${label}`;
  return label;
}

function ResourceSwitch({
  query,
  labels,
}: {
  query: ParsedCatalogQuery;
  labels: CatalogFiltersProps["labels"];
}) {
  const options: Array<[CatalogResource, string]> = [
    ["components", labels.components],
    ["setups", labels.setups],
    ["all", labels.resourceBoth ?? "Both"],
  ];
  return (
    <Control label={labels.resourceLegend}>
      <select
        name="resource"
        defaultValue={query.resource}
        className="bg-background h-11 w-full rounded-sm border px-3 text-sm"
      >
        {options.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
    </Control>
  );
}

function DisclosureButton({
  open,
  controls,
  ui,
  label,
  onToggle,
  children,
}: {
  open: boolean;
  controls: string;
  ui: string;
  label: string;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <Button
      type="button"
      variant={open ? "default" : "outline"}
      aria-expanded={open}
      aria-controls={controls}
      aria-label={label}
      title={label}
      data-ui={ui}
      size="icon"
      className="h-11 w-11"
      onClick={onToggle}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.preventDefault();
          onToggle();
        }
      }}
    >
      {children}
    </Button>
  );
}

function Control({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-xs font-medium">
      {label}
      {children}
    </label>
  );
}

export type { CatalogResource };
