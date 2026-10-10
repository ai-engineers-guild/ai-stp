"use client";

import { useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { Label } from "@/components/atoms/label";
import { Select } from "@/components/atoms/select";
import { ExpandableSearch } from "@/components/molecules/expandable-search";
import { RefineSurface } from "@/components/molecules/filter-surface";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { Link, useRouter } from "@/lib/i18n/navigation";
import type { CorporateContext, CategoryView } from "@/lib/api/generated/types.gen";
import { Icon } from "@/theme";
import { useTechnologyTaxonomy } from "@/lib/technology-taxonomy";

const SINGLE_FILTERS = [
  "category_id",
  "team_id",
  "review",
  "context",
  "freshness",
  "adoption",
  "lifecycle",
] as const;

type SingleFilter = (typeof SINGLE_FILTERS)[number];

function landscapeQuery(filters: Record<string, string | string[]>) {
  const query = new URLSearchParams();
  for (const [name, value] of Object.entries(filters))
    for (const entry of [value].flat()) query.append(name, entry);
  query.delete("offset");
  return query;
}

function landscapeHref(params: URLSearchParams) {
  const text = params.toString();
  return `/corporate/technology-landscape${text ? `?${text}` : ""}`;
}

function viewHref(filters: Record<string, string | string[]>, next: string) {
  const params = landscapeQuery(filters);
  params.set("view", next);
  return landscapeHref(params);
}

export function TechnologyLandscapeFilters({
  filters,
  context,
  categories = [],
  launch,
}: {
  filters: Record<string, string | string[]>;
  context: CorporateContext;
  categories?: CategoryView[];
  launch?: ReactNode;
}) {
  const t = useTranslations("technology");
  const w = useTranslations("technology.workspace");
  const h = useTranslations("hub");
  const router = useRouter();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [queryDraft, setQueryDraft] = useState(
    typeof filters.query === "string" ? filters.query : "",
  );
  const view = filters.view === "table" ? "table" : "grouped";
  const activeCount =
    [filters.project_ids ?? filters.project_id ?? []].flat().filter(Boolean).length +
    SINGLE_FILTERS.filter((key) => typeof filters[key] === "string" && filters[key]).length;

  function push(mutate: (params: URLSearchParams) => void) {
    const params = landscapeQuery(filters);
    mutate(params);
    router.push(landscapeHref(params));
  }

  return (
    <>
      <div className="technology-toolbar">
        <ExpandableSearch
          id="landscape-search"
          value={queryDraft}
          onChange={setQueryDraft}
          onSubmit={() => {
            push((params) => {
              params.delete("query");
              const needle = queryDraft.trim();
              if (needle) params.set("query", needle);
            });
          }}
          label={h("openSearch")}
          fieldLabel={w("searchTechnology")}
          placeholder={w("searchTechnology")}
        />
        <Button
          variant="outline"
          aria-expanded={filtersOpen}
          aria-controls="landscape-filters"
          onClick={() => {
            setFiltersOpen((open) => !open);
          }}
        >
          <Icon name="filter" size="sm" />
          {activeCount ? `${t("filters")} (${activeCount})` : t("filters")}
        </Button>
        <div className="technology-view-switch" aria-label={t("view")}>
          <Button asChild variant="ghost" className={view === "grouped" ? "technology-active" : ""}>
            <Link
              href={viewHref(filters, "grouped")}
              aria-current={view === "grouped" ? "page" : undefined}
            >
              <Icon name="cards" size="sm" />
              {w("map")}
            </Link>
          </Button>
          <Button asChild variant="ghost" className={view === "table" ? "technology-active" : ""}>
            <Link
              href={viewHref(filters, "table")}
              aria-current={view === "table" ? "page" : undefined}
            >
              <Icon name="list" size="sm" />
              {w("table")}
            </Link>
          </Button>
        </div>
        {launch}
      </div>
      {filtersOpen ? (
        <LandscapeFilterSurface
          filters={filters}
          context={context}
          categories={categories}
          onApply={(next) => {
            push(next);
            setFiltersOpen(false);
          }}
          onClose={() => {
            setFiltersOpen(false);
          }}
        />
      ) : null}
    </>
  );
}

function LandscapeFilterSurface({
  filters,
  context,
  categories,
  onApply,
  onClose,
}: {
  filters: Record<string, string | string[]>;
  context: CorporateContext;
  categories: CategoryView[];
  onApply: (mutate: (params: URLSearchParams) => void) => void;
  onClose: () => void;
}) {
  const t = useTranslations("technology");
  const w = useTranslations("technology.workspace");
  const localize = useTechnologyTaxonomy();
  const [projects, setProjects] = useState<string[]>(
    [filters.project_ids ?? filters.project_id ?? []].flat().filter(Boolean),
  );
  const [singles, setSingles] = useState<Record<SingleFilter, string>>(() =>
    Object.fromEntries(
      SINGLE_FILTERS.map((key) => [key, typeof filters[key] === "string" ? filters[key] : ""]),
    ) as Record<SingleFilter, string>,
  );
  const singleOptions: Record<SingleFilter, { value: string; label: string }[]> = {
    category_id: categories.map((c) => ({ value: c.category_id, label: localize(c).name })),
    team_id: context.teams.map((c) => ({ value: c.team_id, label: c.name })),
    review: ["proposed", "confirmed", "rejected", "overridden"].map((value) => ({
      value,
      label: t(`values.${value}`),
    })),
    context: ["production", "development", "testing", "browser_support"].map((value) => ({
      value,
      label: t(`values.${value}`),
    })),
    freshness: ["current", "stale", "absent", "unknown"].map((value) => ({
      value,
      label: t(`values.${value}`),
    })),
    adoption: ["adopt", "trial", "assess", "hold"].map((value) => ({
      value,
      label: t(`values.${value}`),
    })),
    lifecycle: ["draft", "active", "deprecated", "archived"].map((value) => ({
      value,
      label: t(`values.${value}`),
    })),
  };
  return (
    <RefineSurface
      id="landscape-filters"
      labels={{ filtersButton: t("filters"), closeFilters: t("close") }}
      onClose={onClose}
    >
      <p className="text-muted-foreground -mt-3 mb-4 text-sm">{w("filterDescription")}</p>
      <div className="grid min-w-0 items-start gap-5 md:grid-cols-2">
        <div className="min-w-0 space-y-2 text-sm">
          <Label htmlFor="landscape-organization" className="font-medium">
            {w("organization")}
          </Label>
          <Select
            id="landscape-organization"
            value={context.organization.organization_id}
            onChange={() => {}}
          >
            <option value={context.organization.organization_id}>{w("allOrganization")}</option>
          </Select>
        </div>
        <div className="min-w-0 space-y-2 text-sm">
          <span className="font-medium">{w("allProjects")}</span>
          <SearchableMultiSelect
            name="project_ids"
            label={w("allProjects")}
            searchLabel={w("searchProject")}
            options={context.projects.map((p) => ({ value: p.project_id, label: p.name }))}
            selected={projects}
            onChange={setProjects}
            modal
            closeLabel={t("close")}
            emptyHint={w("allProjects")}
          />
        </div>
        {SINGLE_FILTERS.map((name) => (
          <div key={name} className="min-w-0 space-y-2 text-sm">
            <Label htmlFor={`landscape-${name}`} className="font-medium">
              {t(name === "category_id" ? "category" : name === "team_id" ? "team" : name)}
            </Label>
            <Select
              id={`landscape-${name}`}
              value={singles[name]}
              onChange={(event) => {
                setSingles((previous) => ({ ...previous, [name]: event.target.value }));
              }}
            >
              <option value="">{t("all")}</option>
              {singleOptions[name].map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </div>
        ))}
      </div>
      <div className="border-border bg-card sticky bottom-0 mt-6 flex flex-wrap items-center justify-between gap-3 border-t py-5">
        <Button
          type="button"
          variant="ghost"
          className="underline underline-offset-4"
          onClick={() => {
            setProjects([]);
            setSingles(
              Object.fromEntries(SINGLE_FILTERS.map((key) => [key, ""])) as Record<
                SingleFilter,
                string
              >,
            );
          }}
        >
          {t("reset")}
        </Button>
        <Button
          type="button"
          onClick={() => {
            onApply((params) => {
              params.delete("project_ids");
              params.delete("project_id");
              for (const value of projects) params.append("project_ids", value);
              for (const name of SINGLE_FILTERS) {
                params.delete(name);
                if (singles[name]) params.set(name, singles[name]);
              }
            });
          }}
        >
          <Icon name="filter" size="sm" />
          {t("apply")}
        </Button>
      </div>
    </RefineSurface>
  );
}
