"use client";

import { useState } from "react";
import { OverviewFilterControls } from "./corporate-overview-filters";
import { ComponentUsageView } from "./corporate-overview-usage";
import { useTranslations } from "next-intl";
import { Input } from "@/components/atoms/input";
import { Button } from "@/components/atoms/button";
import { TreeBranch } from "./corporate-overview-row";
import {
  Sheet,
  SheetTrigger,
  SheetContent,
  SheetTitle,
  SheetDescription,
  SheetClose,
} from "@/components/atoms/sheet";
import { Icon } from "@/theme";
import type { CorporateOverview } from "@/lib/api/generated/types.gen";
import {
  nodeTechnologies,
  overviewForest,
  type OverviewBranch,
  type OverviewFilters,
} from "@/lib/corporate-overview";

const kinds = ["project", "team", "employee"] as const;
const emptyFilters = (): OverviewFilters => ({ project: [], team: [], employee: [] });

export function CorporateOverviewTree({ graph }: { graph: CorporateOverview }) {
  const t = useTranslations("hub");
  const [view, setView] = useState("organization");
  const [filters, setFilters] = useState(emptyFilters);
  const [query, setQuery] = useState("");
  const [depth, setDepth] = useState(2);
  const [usageExpanded, setUsageExpanded] = useState(false);
  const [sort, setSort] = useState("name");
  const [technologies, setTechnologies] = useState<string[]>([]);
  const [owners, setOwners] = useState<string[]>([]);
  const fullyExpanded = view === "organization" ? depth >= 3 : usageExpanded;
  const resetFilters = () => {
    setFilters(emptyFilters());
    setQuery("");
    setTechnologies([]);
    setOwners([]);
  };
  const controls = (
    <OverviewFilterControls
      graph={graph}
      view={view}
      filters={filters}
      setFilters={setFilters}
      technologies={technologies}
      setTechnologies={setTechnologies}
      owners={owners}
      setOwners={setOwners}
    />
  );
  const filteredGraph = technologies.length
    ? {
        ...graph,
        nodes: graph.nodes.map((node) =>
          nodeTechnologies(node).some((item) => technologies.includes(item.id))
            ? node
            : { ...node, assignments: [] },
        ),
      }
    : graph;
  return (
    <section
      aria-labelledby="corporate-structure-title"
      aria-describedby="corporate-shared-hint"
      className="space-y-4"
    >
      <OverviewHeading
        view={view}
        onCollapse={() => {
          if (view === "organization") setDepth(fullyExpanded ? 0 : 3);
          else setUsageExpanded(!fullyExpanded);
        }}
        onChange={(value) => {
          setView(value);
          resetFilters();
        }}
        fullyExpanded={fullyExpanded}
      />
      <div className="border-border bg-card flex flex-wrap items-center gap-3 rounded-lg border p-3">
        <div className="relative w-full min-w-0 md:w-auto md:flex-1">
          <Icon name="search" size="sm" className="text-muted-foreground absolute top-3.5 left-3" />
          <Input
            aria-label={t(view === "organization" ? "searchStructure" : "searchUsage")}
            placeholder={t(view === "organization" ? "searchStructure" : "searchUsage")}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
            }}
            className="min-h-11 pl-9"
          />
        </div>
        <div className="hidden max-w-full min-w-0 flex-wrap gap-2 md:flex">{controls}</div>
        <div className="md:hidden">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline">
                <Icon name="filter" size="sm" />
                {t("filters")}
              </Button>
            </SheetTrigger>
            <SheetContent className="overflow-y-auto p-4">
              <SheetTitle>{t("filters")}</SheetTitle>
              <SheetDescription>{t("searchStructure")}</SheetDescription>
              {controls}
              <SheetClose asChild>
                <Button variant="outline">{t("closeFilters")}</Button>
              </SheetClose>
            </SheetContent>
          </Sheet>
        </div>
        <label className="flex min-h-11 w-full items-center gap-2 text-sm md:ml-auto md:w-auto">
          {t(view === "organization" ? "expandTo" : "sortBy")}
          <select
            aria-label={t(view === "organization" ? "expandTo" : "sortBy")}
            className="border-input bg-background focus-visible:ring-ring min-h-11 min-w-0 flex-1 rounded-sm border px-3 focus-visible:ring-2 md:flex-none"
            value={view === "organization" ? depth : sort}
            onChange={(event) => {
              if (view === "organization") setDepth(Number(event.target.value));
              else setSort(event.target.value);
            }}
          >
            {view === "organization"
              ? ["collapsed", "projects", "teams", "employees"].map((label, index) => (
                  <option key={label} value={index}>
                    {t(label)}
                  </option>
                ))
              : ["name", "usage"].map((value) => (
                  <option key={value} value={value}>
                    {t(value === "name" ? "sortName" : "sortUsage")}
                  </option>
                ))}
          </select>
        </label>
        {(query.trim() ||
          technologies.length ||
          owners.length ||
          kinds.some((item) => filters[item].length)) && (
          <Button variant="ghost" onClick={resetFilters}>
            {t("clearFilters")}
          </Button>
        )}
      </div>
      {view === "organization" ? (
        <>
          <OrganizationTree
            graph={graph}
            filters={filters}
            query={query}
            depth={depth}
            technologies={technologies}
          />
        </>
      ) : (
        <ComponentUsageView
          graph={filteredGraph}
          query={query}
          teams={filters.team}
          sort={sort}
          owners={owners}
          expandAll={usageExpanded}
        />
      )}
    </section>
  );
}

function OrganizationTree({
  graph,
  filters,
  query,
  depth,
  technologies,
}: {
  graph: CorporateOverview;
  filters: OverviewFilters;
  query: string;
  depth: number;
  technologies: string[];
}) {
  const t = useTranslations("hub");
  function retain(branch: OverviewBranch): OverviewBranch | null {
    const children = branch.children.flatMap((child) => retain(child) ?? []);
    return !technologies.length ||
      nodeTechnologies(branch.node).some((item) => technologies.includes(item.id)) ||
      children.length
      ? { ...branch, children }
      : null;
  }
  const forest = overviewForest(graph, filters, query).flatMap((branch) => retain(branch) ?? []);
  return forest.length ? (
    <ul key={depth} className="space-y-3" data-ui="corporate-overview-tree">
      {forest.map((branch, index) => (
        <TreeBranch
          key={branch.node.id}
          branch={branch}
          depth={depth}
          level={0}
          nodes={graph.nodes}
          initiallyOpen={index === 0}
        />
      ))}
    </ul>
  ) : (
    <p role="status" className="text-muted-foreground rounded-lg border p-6">
      {graph.nodes.length ? t("noMatches") : t("empty")}
    </p>
  );
}

function OverviewHeading({
  view,
  onChange,
  onCollapse,
  fullyExpanded,
}: {
  view: string;
  onChange: (value: string) => void;
  onCollapse: () => void;
  fullyExpanded: boolean;
}) {
  const t = useTranslations("hub");
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <p id="corporate-shared-hint" className="sr-only">
        {t("sharedNodesHint")}
      </p>
      <div>
        <h2 id="corporate-structure-title" className="text-2xl font-medium tracking-tight">
          {t("structure")}
        </h2>
        <p className="text-muted-foreground mt-1 text-sm">
          {t(view === "organization" ? "organizationViewBody" : "usageViewBody")}
        </p>
      </div>
      <div className="flex w-full flex-wrap items-center justify-between gap-3 lg:w-auto lg:justify-end">
        <Button variant="ghost" size="sm" onClick={onCollapse}>
          <Icon name="list" size="sm" />
          {t(fullyExpanded ? "collapseAll" : "expandAll")}
        </Button>
        <div
          className="border-border inline-grid min-w-0 flex-1 grid-cols-2 rounded-sm border p-1 lg:w-auto lg:flex-none"
          role="group"
          aria-label={t("overviewView")}
        >
          {["organization", "components"].map((value) => (
            <Button
              key={value}
              variant={view === value ? "secondary" : "ghost"}
              aria-pressed={view === value}
              className="min-w-0 justify-center whitespace-nowrap"
              onClick={() => {
                onChange(value);
              }}
            >
              {t(value === "organization" ? "byOrganization" : "byComponents")}
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
}
