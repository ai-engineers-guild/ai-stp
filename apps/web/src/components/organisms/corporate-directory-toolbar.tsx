"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { RefineSurface } from "@/components/molecules/filter-surface";
import { cn } from "@/lib/cn";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";
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
import type { CorporateDirectoryFacets } from "@/lib/api/generated/types.gen";

type Selected = Partial<Record<DirectoryFacet, string[]>>;

type Props = {
  resource: DirectoryResource;
  items: readonly DirectoryItem[];
  query: string;

  selected: Selected;
  leadOnly: boolean;
  view: "list" | "cards";
  sort: "name" | "name_desc";
  onQueryChange: (value: string) => void;

  onFacetChange: (facet: DirectoryFacet, values: string[]) => void;
  onLeadOnlyChange: (value: boolean) => void;
  onViewChange: (value: "list" | "cards") => void;
  onSortChange: (value: "name" | "name_desc") => void;
  catalogFacets?: readonly CorporateCatalogFacetConfig[];
  catalogSelected?: Partial<Record<CorporateCatalogFacet, string[]>>;
  onCatalogApply?: (values: Partial<Record<CorporateCatalogFacet, string[]>>) => void;
  addLabel?: string | undefined;
  cancelLabel?: string | undefined;
  adding?: boolean | undefined;
  onAdd?: (() => void) | undefined;
  addHref?: string | undefined;
  facets?: CorporateDirectoryFacets;
};

function optionsFor(
  items: readonly DirectoryItem[],
  facet: DirectoryFacet,
  facets?: CorporateDirectoryFacets,
) {
  return [
    ...new Map(
      [
        ...(facets?.[facet] ?? []),
        ...items.flatMap((item) => directoryReferences(item, facet)),
      ].map((ref) => [ref.id, { value: ref.id, label: ref.name }]),
    ).values(),
  ];
}

function activeCount(
  selected: Selected,
  leadOnly: boolean,
  catalogSelected: Partial<Record<CorporateCatalogFacet, string[]>>,
) {
  return (
    Object.values(selected).reduce((total, values) => total + values.length, 0) +
    Object.values(catalogSelected).reduce((total, values) => total + values.length, 0) +
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
  selected,
  leadOnly,
  view,
  sort,
  onQueryChange,
  onFacetChange,
  onLeadOnlyChange,
  onViewChange,
  onSortChange,
  catalogFacets = [],
  catalogSelected = {},
  onCatalogApply,
  addLabel,
  cancelLabel,
  adding = false,
  onAdd,
  addHref,
  facets,
}: Props) {
  const t = useTranslations("hub");
  const catalog = useTranslations("catalog");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(Boolean(query));
  const dialogId = `corporate-${resource}-filters`;
  const count = activeCount(selected, leadOnly, catalogSelected);
  const [draftSelected, setDraftSelected] = useState(selected);
  const [draftLeadOnly, setDraftLeadOnly] = useState(leadOnly);
  const [draftSort, setDraftSort] = useState(sort);
  const [draftCatalogSelected, setDraftCatalogSelected] = useState(catalogSelected);

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
            setDraftSelected(selected);
            setDraftLeadOnly(leadOnly);
            setDraftSort(sort);
            setDraftCatalogSelected(catalogSelected);
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
            onSortChange(sort === "name" ? "name_desc" : "name");
          }}
        >
          <Icon name="sort" size="sm" />
        </Button>
        {addHref && addLabel ? (
          <Button asChild size="lg">
            <Link href={addHref}>
              <span aria-hidden="true" className="text-xl leading-none">
                +
              </span>
              {addLabel}
            </Link>
          </Button>
        ) : onAdd && addLabel ? (
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
        <RefineSurface
          id={dialogId}
          labels={{ filtersButton: catalog("refineButton"), closeFilters: t("closeFilters") }}
          onClose={() => {
            setFiltersOpen(false);
          }}
        >
          {/* Shared catalog surface owns focus, scrolling, dismissal and responsive positioning. */}
          <div className="grid min-w-0 items-start gap-5 md:grid-cols-2">
            {directoryFacets[resource].map((facet) => (
              <label key={facet} className="min-w-0 space-y-2 text-sm">
                <span className="font-medium">{facet === "leads" ? t("teamLeads") : t(facet)}</span>
                <SearchableMultiSelect
                  key={facet}
                  name={directoryFacetParams[facet]}
                  label={facet === "leads" ? t("teamLeads") : t(facet)}
                  searchLabel={`${t("search")}: ${facet === "leads" ? t("teamLeads") : t(facet)}`}
                  options={optionsFor(items, facet, facets)}
                  selected={draftSelected[facet] ?? []}
                  modal
                  closeLabel={t("closeFilters")}
                  onChange={(values) => {
                    setDraftSelected((previous) => ({ ...previous, [facet]: values }));
                  }}
                />
              </label>
            ))}
            {resource === "members" ? (
              <label className="flex min-h-11 items-center gap-2 text-sm sm:col-span-2">
                <input
                  type="checkbox"
                  checked={draftLeadOnly}
                  onChange={(event) => {
                    setDraftLeadOnly(event.target.checked);
                  }}
                />
                {t("lead")}
              </label>
            ) : null}
            {catalogFacets.length ? (
              <div className="border-border bg-muted/30 min-w-0 space-y-4 rounded-lg border p-4 md:col-span-2">
                <h3 className="font-medium">{t("catalogGovernanceFilters")}</h3>
                <div className="grid min-w-0 gap-5 md:grid-cols-2">
                  {catalogFacets.map((facet) => (
                    <label key={facet.key} className="min-w-0 space-y-2 text-sm">
                      <span className="font-medium">{facet.label}</span>
                      <SearchableMultiSelect
                        name={facet.key}
                        label={facet.label}
                        searchLabel={`${t("search")}: ${facet.label}`}
                        options={facet.options}
                        selected={draftCatalogSelected[facet.key] ?? []}
                        multiple={facet.multiple ?? true}
                        modal
                        closeLabel={t("closeFilters")}
                        onChange={(values) => {
                          setDraftCatalogSelected((previous) => ({
                            ...previous,
                            [facet.key]: values,
                          }));
                        }}
                      />
                    </label>
                  ))}
                </div>
              </div>
            ) : null}
            <label className="min-w-0 space-y-2 text-sm">
              <span className="font-medium">{t("sortBy")}</span>
              <select
                value={draftSort}
                onChange={(event) => {
                  setDraftSort(event.target.value as "name" | "name_desc");
                }}
                className="border-input bg-background focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none"
              >
                <option value="name">{t("sortName")}</option>
                <option value="name_desc">{catalog("sortDescending")}</option>
              </select>
            </label>
          </div>
          <div className="border-border bg-card sticky bottom-0 mt-6 flex flex-wrap items-center justify-between gap-3 border-t py-5">
            <Button
              type="button"
              variant="ghost"
              className="underline underline-offset-4"
              onClick={() => {
                setDraftSelected({});
                setDraftLeadOnly(false);
                setDraftSort("name");
                setDraftCatalogSelected({});
              }}
            >
              {catalog("resetAll")}
            </Button>
            <Button
              type="button"
              onClick={() => {
                onLeadOnlyChange(draftLeadOnly);
                onSortChange(draftSort);
                directoryFacets[resource].forEach((facet) => {
                  onFacetChange(facet, draftSelected[facet] ?? []);
                });
                onCatalogApply?.(draftCatalogSelected);
                setFiltersOpen(false);
              }}
            >
              <Icon name="controls" size="sm" />
              {catalog("applyFilters")}
            </Button>
          </div>
        </RefineSurface>
      ) : null}
    </div>
  );
}

export type { Selected as CorporateDirectorySelectedFilters };
