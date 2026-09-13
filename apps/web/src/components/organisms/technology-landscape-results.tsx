import { getTranslations } from "next-intl/server";

import { Button } from "@/components/atoms/button";
import { Link } from "@/lib/i18n/navigation";
import type {
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
  | "unavailable",
  string
>;

export async function TechnologyLandscapeResults({
  landscape,
  filters,
}: {
  landscape: TechnologyLandscapeView;
  filters: Record<string, string>;
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
  };
  if (landscape.filters.view === "grouped") {
    const categories = [
      ...new Set(landscape.items.flatMap((row) => row.technology.category_ids)),
    ].sort();
    return (
      <div className="space-y-6">
        <p className="text-muted-foreground max-w-prose text-sm">{labels.groupedNote}</p>
        {categories.map((category) => (
          <section key={category} className="space-y-3">
            <h2 className="text-xl font-medium break-all">{category}</h2>
            <LandscapeTable
              rows={landscape.items.filter((row) => row.technology.category_ids.includes(category))}
              filters={filters}
              landscape={landscape}
              labels={labels}
            />
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

function LandscapeTable({
  rows,
  filters,
  landscape,
  labels,
}: {
  rows: TechnologyLandscapeRow[];
  filters: Record<string, string>;
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
  filters: Record<string, string>;
  landscape: TechnologyLandscapeView;
  labels: Labels;
}) {
  const offset = landscape.filters.project_offset ?? 0;
  const limit = landscape.filters.project_limit ?? 128;
  function href(next: number) {
    return `/corporate/technology-landscape?${new URLSearchParams({ ...filters, technology_id: row.technology.technology_id, offset: "0", project_offset: String(next) })}`;
  }
  return (
    <div className="space-y-2">
      <ul className="mt-2 space-y-1">
        {row.projects.map((project) => (
          <li key={project.project_id}>
            <Link
              className="inline-flex min-h-11 items-center underline underline-offset-4"
              href={`/corporate/projects/${project.project_id}?${new URLSearchParams(filters)}`}
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
