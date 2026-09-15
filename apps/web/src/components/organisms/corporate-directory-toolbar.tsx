"use client";

import { useEffect, useId, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { cn } from "@/lib/cn";
import { Icon } from "@/theme";
import {
  directoryFacetParams,
  directoryFacets,
  directoryReferences,
  type DirectoryFacet,
  type DirectoryItem,
  type DirectoryResource,
} from "./corporate-directory-types";

type Selected = Partial<Record<DirectoryFacet, string[]>>;

type Props = {
  resource: DirectoryResource;
  items: readonly DirectoryItem[];
  query: string;
  status: string;
  selected: Selected;
  leadOnly: boolean;
  view: "list" | "cards";
  sort: "name" | "state";
  onQueryChange: (value: string) => void;
  onStatusChange: (value: string) => void;
  onFacetChange: (facet: DirectoryFacet, values: string[]) => void;
  onLeadOnlyChange: (value: boolean) => void;
  onViewChange: (value: "list" | "cards") => void;
  onSortChange: (value: "name" | "state") => void;
  addLabel?: string | undefined;
  cancelLabel?: string | undefined;
  adding?: boolean | undefined;
  onAdd?: (() => void) | undefined;
};

function optionsFor(items: readonly DirectoryItem[], facet: DirectoryFacet) {
  return [
    ...new Map(
      items
        .flatMap((item) => directoryReferences(item, facet))
        .map((ref) => [ref.id, { value: ref.id, label: ref.name }]),
    ).values(),
  ];
}

function activeCount(selected: Selected, status: string, leadOnly: boolean) {
  return (
    Object.values(selected).reduce((total, values) => total + values.length, 0) +
    (status ? 1 : 0) +
    (leadOnly ? 1 : 0)
  );
}

function SearchField({
  query,
  open,
  onChange,
}: {
  query: string;
  open: boolean;
  onChange: (value: string) => void;
}) {
  const t = useTranslations("hub");
  return (
    <div className={cn("border-border bg-card rounded-lg border p-3", !open && "sr-only")}>
      <label htmlFor="directory-search" className="space-y-1.5 text-sm font-medium">
        <span>{t("search")}</span>
        <span className="relative block">
          <Icon
            name="search"
            size="sm"
            className="text-muted-foreground absolute top-1/2 left-3 -translate-y-1/2"
          />
          <Input
            id="directory-search"
            value={query}
            onChange={(event) => {
              onChange(event.target.value);
            }}
            placeholder={t("search")}
            className="h-11 pl-10"
          />
        </span>
      </label>
    </div>
  );
}

// eslint-disable-next-line max-lines-per-function
export function CorporateDirectoryToolbar({
  resource,
  items,
  query,
  status,
  selected,
  leadOnly,
  view,
  sort,
  onQueryChange,
  onStatusChange,
  onFacetChange,
  onLeadOnlyChange,
  onViewChange,
  onSortChange,
  addLabel,
  cancelLabel,
  adding = false,
  onAdd,
}: Props) {
  const t = useTranslations("hub");
  const catalog = useTranslations("catalog");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(Boolean(query));
  const dialogId = useId();
  const count = activeCount(selected, status, leadOnly);
  const states = [...new Set(items.map((item) => item.state))];

  useEffect(() => {
    if (!filtersOpen) return;
    function close(event: KeyboardEvent) {
      if (event.key === "Escape") setFiltersOpen(false);
    }
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("keydown", close);
    };
  }, [filtersOpen]);

  return (
    <div className="space-y-3">
      <div className="flex min-w-0 flex-wrap items-center justify-end gap-3">
        <Button
          type="button"
          variant={searchOpen ? "default" : "outline"}
          size="icon"
          aria-expanded={searchOpen}
          aria-label={t("openSearch")}
          title={t("search")}
          onClick={() => {
            setSearchOpen((open) => !open);
          }}
        >
          <Icon name="search" size="sm" />
        </Button>
        <Button
          type="button"
          variant={filtersOpen || count ? "default" : "outline"}
          size="icon"
          aria-expanded={filtersOpen}
          aria-controls={dialogId}
          aria-label={`${t("filters")}${count ? ` (${count})` : ""}`}
          title={t("filters")}
          onClick={() => {
            setFiltersOpen((open) => !open);
          }}
        >
          <Icon name="controls" size="sm" />
        </Button>
        <div className="flex shrink-0 gap-2" aria-label={catalog("viewLabel")}>
          {(["list", "cards"] as const).map((mode) => (
            <Button
              key={mode}
              type="button"
              variant={view === mode ? "secondary" : "outline"}
              size="icon"
              aria-label={catalog(mode === "list" ? "listView" : "cardsView")}
              aria-pressed={view === mode}
              onClick={() => {
                onViewChange(mode);
              }}
            >
              <Icon name={mode} size="sm" />
            </Button>
          ))}
        </div>
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label={t("sortBy")}
          title={t("sortBy")}
          onClick={() => {
            onSortChange(sort === "name" ? "state" : "name");
          }}
        >
          <Icon name="sort" size="sm" />
        </Button>
        {onAdd && addLabel ? (
          <Button type="button" size="lg" onClick={onAdd}>
            <span aria-hidden="true" className="text-xl leading-none">
              {adding ? "×" : "+"}
            </span>
            {adding ? (cancelLabel ?? addLabel) : addLabel}
          </Button>
        ) : null}
      </div>
      <SearchField query={query} open={searchOpen} onChange={onQueryChange} />
      {filtersOpen ? (
        <>
          <button
            type="button"
            aria-label={t("closeFilters")}
            className="bg-foreground/40 fixed inset-0 z-[60]"
            onClick={() => {
              setFiltersOpen(false);
            }}
          />
          <section
            id={dialogId}
            role="dialog"
            aria-modal="true"
            aria-labelledby={`${dialogId}-title`}
            className="border-border bg-card fixed inset-x-0 bottom-0 z-[70] max-h-[min(92dvh,calc(100vh-1rem))] overflow-y-auto rounded-t-lg border p-4 shadow-md md:inset-x-auto md:top-1/2 md:left-1/2 md:w-[min(42rem,calc(100vw-2rem))] md:-translate-x-1/2 md:-translate-y-1/2 md:rounded-lg md:p-6"
          >
            <div className="border-border mb-5 flex items-center justify-between gap-3 border-b pb-4">
              <h2 id={`${dialogId}-title`} className="text-lg font-medium">
                {t("filters")}
              </h2>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={t("closeFilters")}
                onClick={() => {
                  setFiltersOpen(false);
                }}
              >
                <Icon name="close" size="sm" />
              </Button>
            </div>
            <div className="grid min-w-0 gap-4 sm:grid-cols-2">
              <label className="min-w-0 space-y-2 text-sm">
                <span className="font-medium">{t("status")}</span>
                <select
                  id="directory-status"
                  value={status}
                  onChange={(event) => {
                    onStatusChange(event.target.value);
                  }}
                  className="border-input bg-background focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
                >
                  <option value="">{t("all")}</option>
                  {states.map((value) => (
                    <option key={value} value={value}>
                      {t(value)}
                    </option>
                  ))}
                </select>
              </label>
              {directoryFacets[resource].map((facet) => (
                <SearchableMultiSelect
                  key={facet}
                  name={directoryFacetParams[facet]}
                  label={facet === "leads" ? t("teamLeads") : t(facet)}
                  searchLabel={`${t("search")}: ${facet === "leads" ? t("teamLeads") : t(facet)}`}
                  options={optionsFor(items, facet)}
                  selected={selected[facet] ?? []}
                  modal
                  closeLabel={t("closeFilters")}
                  onChange={(values) => {
                    onFacetChange(facet, values);
                  }}
                />
              ))}
              {resource === "members" ? (
                <label className="flex min-h-11 items-center gap-2 text-sm sm:col-span-2">
                  <input
                    type="checkbox"
                    checked={leadOnly}
                    onChange={(event) => {
                      onLeadOnlyChange(event.target.checked);
                    }}
                  />
                  {t("lead")}
                </label>
              ) : null}
              <label className="min-w-0 space-y-2 text-sm">
                <span className="font-medium">{t("sortBy")}</span>
                <select
                  value={sort}
                  onChange={(event) => {
                    onSortChange(event.target.value as "name" | "state");
                  }}
                  className="border-input bg-background focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
                >
                  <option value="name">{t("sortName")}</option>
                  <option value="state">{t("sortState")}</option>
                </select>
              </label>
            </div>
            <div className="border-border mt-6 flex flex-wrap justify-between gap-3 border-t pt-5">
              {count ? (
                <Button
                  type="button"
                  variant="ghost"
                  className="underline underline-offset-4"
                  onClick={() => {
                    onStatusChange("");
                    onLeadOnlyChange(false);
                    directoryFacets[resource].forEach((facet) => {
                      onFacetChange(facet, []);
                    });
                  }}
                >
                  {t("clearFilters")}
                </Button>
              ) : null}
              <Button
                type="button"
                onClick={() => {
                  setFiltersOpen(false);
                }}
              >
                {t("closeFilters")}
              </Button>
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}

export type { Selected as CorporateDirectorySelectedFilters };
