"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Select } from "@/components/atoms/select";
import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/atoms/dialog";
import { PagePager } from "@/components/molecules/page-pager";
import { Link } from "@/lib/i18n/navigation";
import type {
  AreaView,
  CategoryView,
  TechnologyLandscapeRow,
  TechnologyLandscapeView,
} from "@/lib/api/generated/types.gen";
import { Icon, type IconName } from "@/theme";
import { displayCategoryIds, useTechnologyTaxonomy } from "@/lib/technology-taxonomy";

function versions(row: TechnologyLandscapeRow) {
  return (
    [
      ...new Set(
        row.projects.flatMap((p) =>
          p.usage.facts
            .filter((f) => f.review !== "rejected" && f.freshness !== "absent")
            .map((f) => f.version)
            .filter(Boolean),
        ),
      ),
    ]
      .sort()
      .join(", ") || "—"
  );
}
const areaIcons: IconName[] = [
  "code",
  "devices",
  "component",
  "link",
  "technology",
  "chart",
  "brain",
  "objects",
  "network",
  "shield",
  "controls",
  "setup",
  "technology",
];

function useLandscapePresentation({
  landscape,
  filters,
  categories = null,
  areas = null,
}: {
  landscape: TechnologyLandscapeView;
  filters: Record<string, string | string[]>;
  categories?: CategoryView[] | null;
  areas?: AreaView[] | null;
}) {
  const t = useTranslations("technology");
  const w = useTranslations("technology.workspace");
  const a = useTranslations("technology.areas");
  const localize = useTechnologyTaxonomy();
  const [active, setActive] = useState<TechnologyLandscapeRow | null>(null);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(12);
  const [sort, setSort] = useState({ key: "name", descending: false });
  const categoryById = new Map(categories?.map((c) => [c.category_id, localize(c)]) ?? []);
  const areaById = new Map(areas?.map((a) => [a.area_id, localize(a)]) ?? []);
  function classification(row: TechnologyLandscapeRow, area: boolean) {
    return (
      [
        ...new Set(
          displayCategoryIds(row.technology, categoryById)
            .map((id) => {
              const c = categoryById.get(id);
              return area ? areaById.get(c?.area_id ?? "")?.name : c?.name;
            })
            .filter(Boolean),
        ),
      ].join(", ") || a("unclassified")
    );
  }
  const grouped = filters.view !== "table";
  const groups = new Map<string, Map<string, TechnologyLandscapeRow[]>>();
  for (const area of [...areaById.values()]
    .filter((area) => area.state !== "archived")
    .sort((left, right) => left.area_id.localeCompare(right.area_id)))
    groups.set(area.name, new Map());
  for (const row of landscape.items)
    for (const id of displayCategoryIds(row.technology, categoryById).length
      ? displayCategoryIds(row.technology, categoryById)
      : [""]) {
      const c = categoryById.get(id);
      const area = areaById.get(c?.area_id ?? "")?.name ?? a("unclassified");
      const bucket = groups.get(area) ?? new Map<string, TechnologyLandscapeRow[]>();
      const category = c?.name ?? a("unclassified");
      bucket.set(category, [...(bucket.get(category) ?? []), row]);
      groups.set(area, bucket);
    }
  const sorted = [...landscape.items].sort((a, b) => {
    const value = (row: TechnologyLandscapeRow) =>
      sort.key === "projects"
        ? row.project_count
        : sort.key === "area"
          ? classification(row, true)
          : sort.key === "category"
            ? classification(row, false)
            : sort.key === "versions"
              ? versions(row)
              : sort.key === "status"
                ? row.technology.lifecycle
                : row.technology.name;
    const av = value(a),
      bv = value(b);
    return (
      (typeof av === "number" && typeof bv === "number"
        ? av - bv
        : String(av).localeCompare(String(bv))) * (sort.descending ? -1 : 1)
    );
  });
  const totalPages = Math.max(1, Math.ceil(sorted.length / size));
  const currentPage = Math.min(page, totalPages);
  const shown = grouped
    ? sorted.slice(0, 7)
    : sorted.slice((currentPage - 1) * size, currentPage * size);
  return {
    t,
    w,
    active,
    setActive,
    page,
    setPage,
    size,
    setSize,
    sort,
    setSort,
    categoryById,
    areaById,
    classification,
    grouped,
    groups,
    sorted,
    totalPages,
    currentPage,
    shown,
    landscape,
  };
}
type LandscapeState = ReturnType<typeof useLandscapePresentation>;
export function TechnologyLandscapeResults(props: Parameters<typeof useLandscapePresentation>[0]) {
  const state = useLandscapePresentation(props);
  return (
    <div className="space-y-3">
      <TechnologyLandscapeMap state={state} />
      <TechnologyLandscapeSummary state={state} />
      <TechnologyLandscapeDialog state={state} />
    </div>
  );
}

export function TechnologyLandscapeMap({ state }: { state: LandscapeState }) {
  const { w, setActive, grouped, groups } = state;
  return (
    <>
      {grouped && (
        <section>
          <h2 className="text-xl font-medium">{w("landscapeHeading")}</h2>
          <p className="text-muted-foreground mb-3 text-sm">{w("landscapeDescription")}</p>
          <div className="technology-map-grid">
            {[...groups].map(([area, buckets], index) => (
              <section key={area} className="technology-domain">
                <header>
                  <Icon name={areaIcons[index % areaIcons.length] ?? "technology"} />
                  <h3>{area}</h3>
                  <span>{buckets.size}</span>
                </header>
                {!buckets.size && <p className="text-muted-foreground text-xs">{w("emptyArea")}</p>}
                {[...buckets].map(([category, rows]) => (
                  <div key={category} className="space-y-1">
                    <h4 className="text-muted-foreground text-xs">{category}</h4>
                    <div className="flex flex-wrap gap-2">
                      {rows.map((row) => (
                        <Button
                          key={row.technology.technology_id}
                          variant="secondary"
                          className="technology-chip"
                          onClick={() => {
                            setActive(row);
                          }}
                        >
                          {row.technology.name}
                        </Button>
                      ))}
                    </div>
                  </div>
                ))}
              </section>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

export function TechnologyLandscapeSummary({ state }: { state: LandscapeState }) {
  const { t, w, setActive, sort, setSort, classification, grouped, shown, landscape } = state;
  return (
    <>
      <section className={grouped ? "technology-summary-compact" : "technology-summary"}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className={grouped ? "text-base font-medium" : "text-2xl font-medium"}>
              {w("summary")}
            </h2>
            <p className="text-muted-foreground text-sm">{w("summaryDescription")}</p>
          </div>
          {!grouped && (
            <p className="text-muted-foreground text-xs">
              {w("shown", { count: shown.length, total: landscape.total })}
            </p>
          )}
        </div>
        <div
          className="technology-table-frame"
          role="region"
          aria-label={w("summary")}
          // The scroll region must remain keyboard accessible on narrow screens.
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
          tabIndex={0}
        >
          <Table>
            <caption className="sr-only">{w("summary")}</caption>
            <THead>
              <Tr>
                {[
                  ["name", t("technology")],
                  ["area", w("area")],
                  ["category", w("category")],
                  ["versions", w("versions")],
                  ["projects", t("projects")],
                  ["status", w("status")],
                ].map(([key, label]) => (
                  <Th key={key}>
                    <Button
                      variant="ghost"
                      className="h-auto min-h-8 justify-start p-0 text-xs"
                      onClick={() => {
                        setSort({
                          key: key ?? "name",
                          descending: sort.key === key ? !sort.descending : false,
                        });
                      }}
                    >
                      {label}
                      <Icon name="sort" size="sm" />
                    </Button>
                  </Th>
                ))}
                <Th>
                  <span className="sr-only">{w("actions")}</span>
                </Th>
              </Tr>
            </THead>
            <TBody>
              {shown.map((row) => (
                <Tr key={row.technology.technology_id}>
                  <Td>
                    <Button
                      variant="ghost"
                      className="h-auto min-h-8 p-0 font-medium"
                      onClick={() => {
                        setActive(row);
                      }}
                    >
                      {row.technology.name}
                    </Button>
                  </Td>
                  <Td>{classification(row, true)}</Td>
                  <Td>{classification(row, false)}</Td>
                  <Td>{versions(row)}</Td>
                  <Td>
                    <Button
                      variant="ghost"
                      className="h-auto min-h-8 p-0"
                      onClick={() => {
                        setActive(row);
                      }}
                    >
                      {row.project_count}
                    </Button>
                  </Td>
                  <Td>
                    <Badge variant="secondary">
                      {row.technology.lifecycle === "draft"
                        ? w("draft")
                        : row.proposed_project_count
                          ? w("review")
                          : w("standard")}
                    </Badge>
                  </Td>
                  <Td>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={w("openTechnology", { name: row.technology.name })}
                      onClick={() => {
                        setActive(row);
                      }}
                    >
                      <Icon name="more" size="sm" />
                    </Button>
                  </Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        </div>
        {!shown.length && (
          <p role="status" className="text-muted-foreground p-6 text-sm">
            {t("empty")}
          </p>
        )}
        {!grouped && <TechnologyLandscapePager state={state} />}
      </section>
    </>
  );
}

export function TechnologyLandscapeDialog({ state }: { state: LandscapeState }) {
  const { t, w, active, setActive, classification } = state;
  return (
    <>
      <Dialog
        open={active !== null}
        onOpenChange={(open) => {
          if (!open) setActive(null);
        }}
      >
        <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
          <DialogTitle>{active?.technology.name}</DialogTitle>
          <DialogDescription>
            {active?.technology.description || w("technologyUsage")}
          </DialogDescription>
          {active && (
            <>
              <p className="text-sm">
                {classification(active, true)} / {classification(active, false)}
              </p>
              <p className="text-sm">
                {w("versions")}: {versions(active)}
              </p>
              <ul className="divide-border divide-y">
                {active.projects.map((project) => (
                  <li key={project.project_id} className="space-y-2 py-3">
                    <Link
                      className="font-medium underline underline-offset-4"
                      href={`/corporate/projects/${project.project_id}`}
                    >
                      {project.name}
                    </Link>
                    {project.usage.facts.map((fact, index) => (
                      <div key={index} className="text-sm">
                        <span>
                          {t(`values.${fact.context}`)} · {fact.version || "—"} ·{" "}
                          {t(`values.${fact.review}`)}
                        </span>
                        <ul className="text-muted-foreground text-xs">
                          {fact.evidence.map((e, i) => (
                            <li key={i}>{e.path ?? e.reference ?? e.source}</li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </li>
                ))}
              </ul>
              <Button asChild variant="outline">
                <Link href={`/corporate/technologies/${active.technology.technology_id}`}>
                  {w("openRegistry")}
                </Link>
              </Button>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

function TechnologyLandscapePager({ state }: { state: LandscapeState }) {
  const { t, w, currentPage, totalPages, setPage, size, setSize, landscape } = state;
  return (
    <PagePager
      label={w("pagination")}
      page={currentPage}
      totalPages={totalPages}
      onPage={setPage}
      controls={{
        previous: t("previous"),
        next: t("next"),
        page: (value) => w("page", { page: value }),
      }}
      summary={
        <div className="flex items-center gap-3 text-sm">
          <span>{w("showPerPage")}</span>
          <Select
            aria-label={w("pageSize")}
            className="w-20"
            value={size}
            onChange={(e) => {
              setSize(Number(e.target.value));
              setPage(1);
            }}
          >
            {[12, 24, 48, 96].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </Select>
          <span>{w("ofTechnologies", { total: landscape.total })}</span>
        </div>
      }
    />
  );
}
