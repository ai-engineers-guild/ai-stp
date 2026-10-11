"use client";

import { useId, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { RefineSurface } from "@/components/molecules/filter-surface";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { cn } from "@/lib/cn";
import { Icon } from "@/theme";

/**
 * Facet-driven filter toolbar for the technology workspace. Mirrors the
 * corporate directory pattern (search toggle + refine surface with draft
 * state, Apply/Reset footer) without its resource-coupled facet wiring.
 * `options` facets open as modal pickers so dense table layouts never clip.
 */
export type TechnologyFilterFacet =
  | {
      kind: "options";
      key: string;
      label: string;
      options: readonly { value: string; label: string }[];
      multiple?: boolean;
      searchLabel?: string;
    }
  | { kind: "date"; key: string; label: string }
  | { kind: "flag"; key: string; label: string };

export type TechnologyFilterValues = Record<string, string[] | string | boolean>;

export function emptyFilterValue(facet: TechnologyFilterFacet): string[] | string | boolean {
  return facet.kind === "options" ? [] : facet.kind === "date" ? "" : false;
}

function activeCount(values: TechnologyFilterValues) {
  return Object.values(values).filter((value) =>
    Array.isArray(value) ? value.length > 0 : Boolean(value),
  ).length;
}

export function TechnologyFilterToolbar({
  search,
  searchPlaceholder,
  onSearchChange,
  facets,
  values,
  onApply,
  onReset,
}: {
  search: string;
  searchPlaceholder: string;
  onSearchChange: (value: string) => void;
  facets: readonly TechnologyFilterFacet[];
  values: TechnologyFilterValues;
  onApply: (values: TechnologyFilterValues) => void;
  onReset?: () => void;
}) {
  const t = useTranslations("technology");
  const hub = useTranslations("hub");
  const catalog = useTranslations("catalog");
  const id = useId();
  const [searchOpen, setSearchOpen] = useState(Boolean(search));
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [draft, setDraft] = useState<TechnologyFilterValues>(values);
  const count = activeCount(values);

  return (
    <div className="space-y-3">
      <div className="flex min-w-0 flex-wrap items-center justify-end gap-3">
        <Button
          type="button"
          variant={searchOpen ? "default" : "outline"}
          size="icon"
          aria-expanded={searchOpen}
          aria-label={hub("openSearch")}
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
          aria-controls={`${id}-filters`}
          aria-label={`${t("filters")}${count ? ` (${count})` : ""}`}
          title={t("filters")}
          onClick={() => {
            setDraft(values);
            setFiltersOpen((open) => !open);
          }}
        >
          <Icon name="controls" size="sm" />
        </Button>
      </div>
      <div className={cn("border-border bg-card rounded-lg border p-3", !searchOpen && "sr-only")}>
        <label htmlFor={`${id}-search`} className="space-y-1.5 text-sm font-medium">
          <span>{t("search")}</span>
          <span className="relative block">
            <Icon
              name="search"
              size="sm"
              className="text-muted-foreground absolute top-1/2 left-3 -translate-y-1/2"
            />
            <Input
              id={`${id}-search`}
              value={search}
              onChange={(event) => {
                onSearchChange(event.target.value);
              }}
              placeholder={searchPlaceholder}
              className="h-11 pl-10"
            />
          </span>
        </label>
      </div>
      {filtersOpen ? (
        <RefineSurface
          id={`${id}-filters`}
          labels={{ filtersButton: t("filters"), closeFilters: t("close") }}
          onClose={() => {
            setFiltersOpen(false);
          }}
        >
          <div className="grid min-w-0 items-start gap-5 md:grid-cols-2">
            {facets.map((facet) => (
              <TechnologyFacetField
                key={facet.key}
                id={id}
                facet={facet}
                value={draft[facet.key]}
                onChange={(value) => {
                  setDraft((previous) => ({ ...previous, [facet.key]: value }));
                }}
              />
            ))}
          </div>
          <div className="border-border bg-card sticky bottom-0 mt-6 flex flex-wrap items-center justify-between gap-3 border-t py-5">
            <Button
              type="button"
              variant="ghost"
              className="underline underline-offset-4"
              onClick={() => {
                setDraft(
                  Object.fromEntries(facets.map((facet) => [facet.key, emptyFilterValue(facet)])),
                );
                onReset?.();
              }}
            >
              {catalog("resetAll")}
            </Button>
            <Button
              type="button"
              onClick={() => {
                onApply(draft);
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

function TechnologyFacetField({
  id,
  facet,
  value,
  onChange,
}: {
  id: string;
  facet: TechnologyFilterFacet;
  value: string[] | string | boolean | undefined;
  onChange: (value: string[] | string | boolean) => void;
}) {
  const t = useTranslations("technology");
  if (facet.kind === "options")
    return (
      <label className="min-w-0 space-y-2 text-sm">
        <span className="font-medium">{facet.label}</span>
        <SearchableMultiSelect
          name={`filter-${facet.key}`}
          label={facet.label}
          searchLabel={facet.searchLabel ?? `${t("search")}: ${facet.label}`}
          options={facet.options}
          selected={(value as string[] | undefined) ?? []}
          multiple={facet.multiple ?? false}
          modal
          closeLabel={t("close")}
          onChange={onChange}
        />
      </label>
    );
  if (facet.kind === "date")
    return (
      <Label htmlFor={`${id}-${facet.key}`} className="min-w-0 space-y-2 text-sm">
        <span className="font-medium">{facet.label}</span>
        <Input
          id={`${id}-${facet.key}`}
          type="date"
          value={(value as string | undefined) ?? ""}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      </Label>
    );
  return (
    <Label className="flex min-h-11 items-center gap-2 text-sm">
      <input
        type="checkbox"
        className="accent-primary size-4"
        checked={Boolean(value)}
        onChange={(event) => {
          onChange(event.target.checked);
        }}
      />
      {facet.label}
    </Label>
  );
}
