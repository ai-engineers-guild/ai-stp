"use client";
import type { Dispatch, SetStateAction } from "react";
import { useTranslations } from "next-intl";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import type { CorporateOverview } from "@/lib/api/generated/types.gen";
import { nodeTechnologies, overviewUsage, type OverviewFilters } from "@/lib/corporate-overview";
const kinds = ["project", "team", "employee"] as const;
const labels = { project: "project", team: "team", employee: "employee" } as const;

export function OverviewFilterControls({
  graph,
  view,
  filters,
  setFilters,
  technologies,
  setTechnologies,
  owners,
  setOwners,
}: {
  graph: CorporateOverview;
  view: string;
  filters: OverviewFilters;
  setFilters: Dispatch<SetStateAction<OverviewFilters>>;
  technologies: string[];
  setTechnologies: (values: string[]) => void;
  owners: string[];
  setOwners: (values: string[]) => void;
}) {
  const t = useTranslations("hub");
  const controls = kinds
    .filter((item) => view === "organization" || item === "team")
    .map((item) => (
      <SearchableMultiSelect
        key={item}
        name={item}
        label={t(labels[item])}
        searchLabel={t("search")}
        options={graph.nodes
          .filter((node) => node.kind === item)
          .map((node) => ({ value: node.id, label: node.name }))}
        selected={filters[item]}
        onChange={(values) => {
          setFilters((current) => ({ ...current, [item]: values }));
        }}
      />
    ));
  controls.push(
    <SearchableMultiSelect
      key="technology"
      name="technology"
      label={t("technologyFilter")}
      searchLabel={t("search")}
      options={[
        ...new Map(
          graph.nodes.flatMap((node) =>
            nodeTechnologies(node).map(
              (item) => [item.id, { value: item.id, label: item.name }] as const,
            ),
          ),
        ).values(),
      ]}
      selected={technologies}
      onChange={setTechnologies}
    />,
  );
  if (view === "components")
    controls.push(
      <SearchableMultiSelect
        key="owner"
        name="owner"
        label={t("operationalOwner")}
        searchLabel={t("search")}
        options={[
          ...new Map(
            overviewUsage(graph).flatMap((row) =>
              typeof row.assignment.owner_name === "string" &&
              typeof row.assignment.owner_id === "string"
                ? [
                    [
                      row.assignment.owner_id,
                      { value: row.assignment.owner_id, label: row.assignment.owner_name },
                    ] as const,
                  ]
                : [],
            ),
          ).values(),
        ]}
        selected={owners}
        onChange={setOwners}
      />,
    );
  return <>{controls}</>;
}
