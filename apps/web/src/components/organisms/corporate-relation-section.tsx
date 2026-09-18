"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/atoms/button";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import { RefineSurface } from "@/components/molecules/filter-surface";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { CorporateDirectoryCard } from "@/components/organisms/corporate-directory-card";
import type {
  CorporateDirectoryFacets,
  CorporateDirectoryQuery,
  CorporateDirectoryView,
} from "@/lib/api/generated/types.gen";
import type {
  DirectoryFacet,
  DirectoryItem,
  DirectoryRef,
  DirectoryResource,
} from "@/components/organisms/corporate-directory-types";
import {
  directoryFacetParams,
  directoryFacets,
  directoryReferences,
} from "@/components/organisms/corporate-directory-types";
import { Icon } from "@/theme";

type Labels = {
  filters: string;
  filterTitle: string;
  filterHint: string;
  reset: string;
  close: string;
  search: string;
  apply: string;
  previous: string;
  next: string;
  page: string;
  noMatches: string;
  moreActions: string;
  owner: string;
  operationalOwner: string;
  teams: string;
  projects: string;
  technologies: string;
  categories: string;
  job_titles?: string;
  teamLeads: string;
  team: string;
  employee: string;
  author: string;
  type: string;
  lead: string;
  unknownEmployee: string;
  notAvailable: string;
};

const PAGE_SIZE = 10;
export type CorporateRelationApi = {
  resource: Exclude<DirectoryResource, "components">;
  filters?: Pick<
    CorporateDirectoryQuery,
    "lead_ids" | "team_ids" | "technology_ids" | "project_ids" | "category_ids"
  >;
  leadOnly?: boolean;
};

type SelectedFilters = Partial<Record<DirectoryFacet, string[]>>;

function facetLabel(labels: Labels, facet: DirectoryFacet) {
  if (facet === "leads") return labels.teamLeads;
  if (facet === "categories") return labels.categories;
  if (facet === "job_titles") return labels.job_titles ?? labels.categories;
  return labels[facet];
}

function relationOptions(
  items: readonly DirectoryItem[],
  facets: CorporateDirectoryFacets | null,
  facet: DirectoryFacet,
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

async function loadRelationPage(
  api: CorporateRelationApi,
  selected: SelectedFilters,
  leadOnly: boolean,
  page: number,
  signal: AbortSignal,
): Promise<CorporateDirectoryView> {
  const params = new URLSearchParams({
    resource: api.resource,
    offset: String(page * PAGE_SIZE),
    limit: String(PAGE_SIZE),
    ...(leadOnly || api.leadOnly ? { is_lead: "true" } : {}),
  });
  for (const [key, value] of Object.entries(api.filters ?? {})) {
    for (const item of value) params.append(key, item);
  }
  for (const [facet, values] of Object.entries(selected)) {
    for (const value of values) params.append(directoryFacetParams[facet as DirectoryFacet], value);
  }
  const response = await fetch(`/api/corporate/directory?${params.toString()}`, {
    signal,
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error("directory request failed");
  return (await response.json()) as CorporateDirectoryView;
}

// eslint-disable-next-line max-lines-per-function
export function CorporateRelationSection({
  title,
  resource,
  references,
  labels,
  api,
}: {
  title: string;
  resource: DirectoryResource;
  references: readonly DirectoryRef[];
  labels: Labels;
  api?: CorporateRelationApi | undefined;
}) {
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [selected, setSelected] = useState<SelectedFilters>({});
  const [draftSelected, setDraftSelected] = useState<SelectedFilters>({});
  const [leadOnly, setLeadOnly] = useState(false);
  const [draftLeadOnly, setDraftLeadOnly] = useState(false);
  const [page, setPage] = useState(0);
  const [remote, setRemote] = useState<{
    items: readonly DirectoryItem[];
    total: number;
    facets: CorporateDirectoryFacets;
  } | null>(null);
  useEffect(() => {
    if (!api) return;
    const controller = new AbortController();
    void loadRelationPage(api, selected, leadOnly, page, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setRemote({ items: data.items, total: data.total, facets: data.facets });
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setRemote(null);
      });
    return () => {
      controller.abort();
    };
  }, [api, leadOnly, page, selected]);
  const filtered = useMemo(() => references, [references]);
  const total = api ? (remote?.total ?? references.length) : filtered.length;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const items: readonly DirectoryItem[] = api
    ? (remote?.items ??
      filtered
        .slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE)
        .map((reference) => ({ id: reference.id, name: reference.name })))
    : filtered
        .slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE)
        .map((reference) => ({ id: reference.id, name: reference.name }));
  const cardLabels = {
    ...labels,
    ownerTeam: labels.owner,
    operationalOwner: labels.operationalOwner,
  };

  return (
    <DetailAccordion title={title} summary={`${total}`} defaultOpen>
      <div className="min-w-0">
        <div className="mb-4 flex justify-end">
          <Button
            type="button"
            variant={
              filtersOpen || Object.values(selected).some((values) => values.length) || leadOnly
                ? "default"
                : "outline"
            }
            size="sm"
            aria-expanded={filtersOpen}
            aria-controls={`relation-filters-${resource}`}
            onClick={() => {
              setDraftSelected(selected);
              setDraftLeadOnly(leadOnly);
              setFiltersOpen((open) => !open);
            }}
          >
            <Icon name="controls" size="sm" />
            {labels.filters}
          </Button>
        </div>
        {filtersOpen ? (
          <RefineSurface
            id={`relation-filters-${resource}`}
            labels={{
              filtersButton: labels.filters,
              refineButton: labels.filterTitle,
              closeFilters: labels.close,
            }}
            onClose={() => {
              setFiltersOpen(false);
            }}
          >
            <div className="grid min-w-0 items-start gap-5 md:grid-cols-2">
              {directoryFacets[resource].map((facet) => (
                <label key={facet} className="min-w-0 space-y-2 text-sm">
                  <span className="font-medium">{facetLabel(labels, facet)}</span>
                  <SearchableMultiSelect
                    name={directoryFacetParams[facet]}
                    label={facetLabel(labels, facet)}
                    searchLabel={labels.search}
                    options={relationOptions(remote?.items ?? [], remote?.facets ?? null, facet)}
                    selected={draftSelected[facet] ?? []}
                    modal
                    closeLabel={labels.close}
                    onChange={(values) => {
                      setDraftSelected((previous) => ({ ...previous, [facet]: values }));
                    }}
                  />
                </label>
              ))}
              {resource === "members" ? (
                <label className="flex min-h-11 items-center gap-2 text-sm md:col-span-2">
                  <input
                    type="checkbox"
                    checked={draftLeadOnly}
                    onChange={(event) => {
                      setDraftLeadOnly(event.target.checked);
                    }}
                  />
                  {labels.lead}
                </label>
              ) : null}
            </div>
            <div className="border-border bg-card sticky bottom-0 mt-6 flex flex-wrap items-center justify-between gap-3 border-t py-5">
              <Button
                type="button"
                variant="ghost"
                className="underline underline-offset-4"
                onClick={() => {
                  setDraftSelected({});
                  setDraftLeadOnly(false);
                }}
              >
                {labels.reset}
              </Button>
              <Button
                type="button"
                onClick={() => {
                  setSelected(draftSelected);
                  setLeadOnly(draftLeadOnly);
                  setPage(0);
                  setFiltersOpen(false);
                }}
              >
                <Icon name="controls" size="sm" />
                {labels.apply}
              </Button>
            </div>
          </RefineSurface>
        ) : null}
        {items.length ? (
          <ul className="min-w-0 space-y-3">
            {items.map((item) => (
              <CorporateDirectoryCard
                key={item.id}
                resource={resource}
                item={item}
                labels={cardLabels}
                returnFilters=""
                view="cards"
              />
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground py-2 text-sm">{labels.noMatches}</p>
        )}
        {total > PAGE_SIZE ? (
          <nav
            className="border-border mt-4 flex items-center justify-between gap-3 border-t pt-4"
            aria-label={title}
          >
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage === 0}
              onClick={() => {
                setPage((value) => Math.max(0, value - 1));
              }}
            >
              {labels.previous}
            </Button>
            <span className="text-muted-foreground text-sm">
              {labels.page} {currentPage + 1} / {pageCount}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage === pageCount - 1}
              onClick={() => {
                setPage((value) => Math.min(pageCount - 1, value + 1));
              }}
            >
              {labels.next}
            </Button>
          </nav>
        ) : null}
      </div>
    </DetailAccordion>
  );
}

export type { Labels as CorporateRelationSectionLabels };
