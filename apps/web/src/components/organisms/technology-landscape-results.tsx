import { getTranslations } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { landscapeSearchParams } from "@/lib/api/technology";
import { Link } from "@/lib/i18n/navigation";
import type {
  AreaView,
  CategoryView,
  TechnologyLandscapeRow,
  TechnologyLandscapeView,
} from "@/lib/api/generated/types.gen";

type Labels = Record<
  | "technology"
  | "projects"
  | "proposed"
  | "previous"
  | "next"
  | "activity"
  | "groupedNote"
  | "decisionUnavailable"
  | "noKnownUse"
  | "active"
  | "inactive"
  | "unknown"
  | "source_availability"
  | "available"
  | "unavailable"
  | "versions"
  | "unclassified",
  string
>;

type Filters = Record<string, string | string[]>;

function filterQuery(filters: Filters, extra: Record<string, string>) {
  const params = new URLSearchParams(landscapeSearchParams(filters));
  for (const [key, value] of Object.entries(extra)) params.set(key, value);
  return params;
}

export async function TechnologyLandscapeResults({
  landscape,
  filters,
  categories = null,
  areas = null,
}: {
  landscape: TechnologyLandscapeView;
  filters: Filters;
  categories?: CategoryView[] | null;
  areas?: AreaView[] | null;
}) {
  const t = await getTranslations("technology");
  const labels: Labels = {
    technology: t("technology"),
    projects: t("projects"),
    proposed: t("proposed"),
    previous: t("previous"),
    next: t("next"),
    activity: t("activity"),
    groupedNote: t("groupedNote"),
    decisionUnavailable: t("decisionUnavailable"),
    noKnownUse: t("noKnownUse"),
    active: t("values.active"),
    inactive: t("values.inactive"),
    unknown: t("values.unknown"),
    source_availability: t("source_availability"),
    available: t("values.available"),
    unavailable: t("values.unavailable"),
    versions: t("scans.columns.version"),
    unclassified: t("areas.unclassified"),
  };
  if (landscape.filters.view === "grouped") {
    const byId = new Map(categories?.map((item) => [item.category_id, item]) ?? []);
    const areaById = new Map(areas?.map((item) => [item.area_id, item]) ?? []);
    const groups = new Map<string, Map<string, TechnologyLandscapeRow[]>>();
    for (const row of landscape.items) {
      const ids = row.technology.category_ids.length ? row.technology.category_ids : [""];
      for (const id of ids) {
        const category = byId.get(id);
        const areaId = category?.area_id ?? "";
        const areaName = areaById.get(areaId)?.name ?? labels.unclassified;
        const bucket = groups.get(areaName) ?? new Map<string, TechnologyLandscapeRow[]>();
        const key = category?.name ?? (id || labels.unclassified);
        bucket.set(key, [...(bucket.get(key) ?? []), row]);
        groups.set(areaName, bucket);
      }
    }
    return (
      <div className="space-y-8">
        <p className="text-muted-foreground max-w-prose text-sm">{labels.groupedNote}</p>
        {[...groups.entries()]
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([area, items]) => (
            <section key={area} className="space-y-4">
              <h2 className="text-2xl font-medium">{area}</h2>
              {[...items.entries()]
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([category, rows]) => (
                  <section key={category} className="space-y-3">
                    <h3 className="text-xl font-medium break-all">{category}</h3>
                    <LandscapeTable
                      rows={rows}
                      filters={filters}
                      landscape={landscape}
                      labels={labels}
                    />
                  </section>
                ))}
            </section>
          ))}
      </div>
    );
  }
  if (landscape.filters.view === "radar") {
    const placements = [null, "none", "assess", "trial", "adopt", "hold"] as const;
    return (
      <div className="space-y-6">
        {placements.map((placement) => {
          const rows = landscape.items.filter(
            (row) => (row.decision?.adoption ?? null) === placement,
          );
          return rows.length ? (
            <section key={placement ?? "unavailable"} className="space-y-3">
              <h2 className="text-xl font-medium">
                {placement === null ? labels.decisionUnavailable : t(`values.${placement}`)}
              </h2>
              <LandscapeTable rows={rows} filters={filters} landscape={landscape} labels={labels} />
            </section>
          ) : null;
        })}
      </div>
    );
  }
  if (landscape.filters.view === "relationships")
    return (
      <ul className="divide-border divide-y">
        {landscape.items.map((row) => (
          <li key={row.technology.technology_id} className="space-y-3 py-4">
            <h2 className="text-xl font-medium">
              <TechnologyLink row={row} />
            </h2>
            <p className="text-sm tabular-nums">
              {labels.projects}: {row.project_count}; {labels.proposed}:{" "}
              {row.proposed_project_count}
            </p>
            <ProjectLinks row={row} filters={filters} landscape={landscape} labels={labels} />
          </li>
        ))}
      </ul>
    );
  return (
    <LandscapeTable
      rows={landscape.items}
      filters={filters}
      landscape={landscape}
      labels={labels}
    />
  );
}

function TechnologyLink({ row }: { row: TechnologyLandscapeRow }) {
  return (
    <Link
      href={`/corporate/technologies/${row.technology.technology_id}`}
      className="inline-flex min-h-11 items-center underline underline-offset-4"
    >
      {row.technology.name}
    </Link>
  );
}

function rowVersions(row: TechnologyLandscapeRow): string[] {
  return [
    ...new Set(
      row.projects.flatMap((project) =>
        project.usage.facts.map((fact) => fact.version).filter(Boolean),
      ),
    ),
  ].sort() as string[];
}

function LandscapeTable({
  rows,
  filters,
  landscape,
  labels,
}: {
  rows: TechnologyLandscapeRow[];
  filters: Filters;
  landscape: TechnologyLandscapeView;
  labels: Labels;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">
          {labels.technology} — {labels.projects}
        </caption>
        <thead className="border-border border-b">
          <tr>
            <th scope="col" className="p-3 font-medium">
              {labels.technology}
            </th>
            <th scope="col" className="p-3 font-medium">
              {labels.versions}
            </th>
            <th scope="col" className="p-3 font-medium">
              {labels.projects}
            </th>
            <th scope="col" className="p-3 font-medium">
              {labels.proposed}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.technology.technology_id} className="border-border border-b align-top">
              <th scope="row" className="p-3 font-medium">
                <TechnologyLink row={row} />
              </th>
              <td className="p-3">
                <span className="flex flex-wrap gap-1">
                  {rowVersions(row).map((version) => (
                    <Badge key={version} variant="outline">
                      <code className="font-mono text-xs">{version}</code>
                    </Badge>
                  ))}
                  {!rowVersions(row).length && "—"}
                </span>
              </td>
              <td className="p-3">
                <span className="tabular-nums">{row.project_count}</span>
                {!row.project_count && !row.proposed_project_count && (
                  <p className="text-muted-foreground mt-2">{labels.noKnownUse}</p>
                )}
                <ProjectLinks row={row} filters={filters} landscape={landscape} labels={labels} />
              </td>
              <td className="p-3 tabular-nums">{row.proposed_project_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProjectLinks({
  row,
  filters,
  landscape,
  labels,
}: {
  row: TechnologyLandscapeRow;
  filters: Filters;
  landscape: TechnologyLandscapeView;
  labels: Labels;
}) {
  const offset = landscape.filters.project_offset ?? 0;
  const limit = landscape.filters.project_limit ?? 128;
  function href(next: number) {
    return `/corporate/technology-landscape?${filterQuery(filters, { technology_id: row.technology.technology_id, offset: "0", project_offset: String(next) })}`;
  }
  return (
    <div className="space-y-2">
      <ul className="mt-2 space-y-1">
        {row.projects.map((project) => (
          <li key={project.project_id}>
            <Link
              className="inline-flex min-h-11 items-center underline underline-offset-4"
              href={`/corporate/projects/${project.project_id}?${filterQuery(filters, {})}`}
            >
              {project.name}
            </Link>
            <span className="text-muted-foreground block text-xs">
              {labels.activity}: {labels[project.activity]}
              {" · "}
              {labels.source_availability}: {labels[project.source_availability ?? "unknown"]}
            </span>
          </li>
        ))}
      </ul>
      <nav
        className="flex flex-wrap gap-2"
        aria-label={`${row.technology.name} — ${labels.projects}`}
      >
        {offset > 0 && (
          <Button asChild size="lg" variant="outline">
            <Link href={href(Math.max(0, offset - limit))}>{labels.previous}</Link>
          </Button>
        )}
        {offset + limit < row.project_count && (
          <Button asChild size="lg" variant="outline">
            <Link href={href(offset + limit)}>{labels.next}</Link>
          </Button>
        )}
      </nav>
    </div>
  );
}
