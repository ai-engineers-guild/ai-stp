"use client";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { Badge } from "@/components/atoms/badge";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";
import type { CorporateOverview } from "@/lib/api/generated/types.gen";
import {
  corporateNodeHref,
  overviewUsage,
  overviewEntityIcons as icons,
  overviewAssignmentHref as assignmentHref,
} from "@/lib/corporate-overview";

export function ComponentUsageView({
  graph,
  query,
  teams,
  sort,
  owners,
  expandAll = false,
}: {
  graph: CorporateOverview;
  query: string;
  teams: string[];
  sort: string;
  owners: string[];
  expandAll?: boolean;
}) {
  const t = useTranslations("hub");
  const rows = overviewUsage(graph)
    .filter(
      (row) =>
        (!owners.length ||
          (typeof row.assignment.owner_id === "string" &&
            owners.includes(row.assignment.owner_id))) &&
        (!teams.length || row.nodes.some((node) => teams.includes(node.id))) &&
        `${row.assignment.display_name ?? ""} ${typeof row.assignment.description === "string" ? row.assignment.description : ""} ${row.nodes.map((node) => node.name).join(" ")}`
          .toLocaleLowerCase()
          .includes(query.trim().toLocaleLowerCase()),
    )
    .sort((a, b) =>
      sort === "usage"
        ? b.nodes.length - a.nodes.length
        : (a.assignment.display_name ?? "").localeCompare(b.assignment.display_name ?? ""),
    );
  return rows.length ? (
    <ul className="border-border bg-card divide-border divide-y overflow-hidden rounded-lg border">
      {rows.map((row) => (
        <ComponentUsageRow
          key={`${row.assignment.stable_id}:${expandAll ? "open" : "closed"}`}
          row={row}
          expandAll={expandAll}
        />
      ))}
    </ul>
  ) : (
    <p role="status" className="border-border text-muted-foreground rounded-lg border p-6">
      {t("noMatches")}
    </p>
  );
}

function ComponentUsageRow({
  row,
  expandAll,
}: {
  row: ReturnType<typeof overviewUsage>[number];
  expandAll: boolean;
}) {
  const t = useTranslations("hub");
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState(expandAll);
  const assignment = row.assignment as typeof row.assignment & {
    author_id?: unknown;
    author_name?: unknown;
    catalog_type?: unknown;
  };
  const authorName = typeof assignment.author_name === "string" ? assignment.author_name : null;
  const catalogType = typeof assignment.catalog_type === "string" ? assignment.catalog_type : null;
  return (
    <li>
      <details
        open={open}
        onToggle={(event) => {
          setOpen(event.currentTarget.open);
        }}
        className="[&[open]>summary>svg]:rotate-180"
      >
        <summary className="hover:bg-muted focus-visible:ring-ring flex cursor-pointer list-none flex-wrap items-start gap-4 p-4 focus-visible:ring-2 [&::-webkit-details-marker]:hidden">
          <span className="bg-muted border-border grid size-11 shrink-0 place-items-center rounded-md border">
            <Icon name={icons[row.assignment.object_kind] ?? "objects"} />
          </span>
          <div className="min-w-0 flex-1">
            <Link
              href={assignmentHref(row.assignment)}
              className="hover:text-primary font-medium break-words hover:underline"
            >
              {row.assignment.display_name || t(row.assignment.object_kind)}
            </Link>
            <div className="mt-2 flex flex-wrap gap-2">
              <Badge variant="secondary">{t(row.assignment.object_kind)}</Badge>
              {catalogType && row.assignment.object_kind === "component" && (
                <Badge variant="outline">{catalogType}</Badge>
              )}
            </div>
            {typeof row.assignment.description === "string" && (
              <p className="text-muted-foreground mt-1 text-xs">{row.assignment.description}</p>
            )}
          </div>
          <div className="text-muted-foreground w-full text-sm sm:w-auto">
            <p className="text-xs">
              {t("author")}: {authorName ?? t("authorUnavailable")}
            </p>
            <p className="text-xs">
              {t("operationalOwner")}:{" "}
              {typeof row.assignment.owner_name === "string" &&
              typeof row.assignment.owner_id === "string" ? (
                <Link
                  href={`/corporate/employees/${encodeURIComponent(row.assignment.owner_id)}`}
                  className="hover:underline"
                >
                  {row.assignment.owner_name}
                </Link>
              ) : (
                t(row.assignment.owner_readable ? "ownerUnassigned" : "ownerUnavailable")
              )}
            </p>
            {t("usedBy")}: {row.nodes.filter((node) => node.kind === "team").length} {t("teams")} /{" "}
            {row.nodes.filter((node) => node.kind === "project").length} {t("projects")}
          </div>
          <Icon name="chevronDown" size="sm" />
        </summary>
        <div className="bg-muted/30 mx-4 mb-4 space-y-3 rounded-md p-3">
          <div className="flex flex-wrap gap-2">
            {row.versions.map((item) => (
              <Link
                key={item.version}
                href={assignmentHref(item)}
                className="border-border bg-background/40 hover:border-primary hover:bg-muted hover:text-primary rounded-md border px-2 py-1 text-xs transition-colors"
              >
                {t("exactVersion")} {item.version}
              </Link>
            ))}
          </div>
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {row.nodes.slice(0, all ? undefined : 6).map((node) => (
              <li key={node.id}>
                <Link
                  href={corporateNodeHref(node)}
                  className="border-border hover:border-primary hover:bg-muted hover:text-primary flex min-h-11 min-w-0 items-center gap-2 rounded-sm border px-3 py-2 text-sm transition-colors"
                >
                  <Icon name={icons[node.kind] ?? "user"} size="sm" />
                  <span className="min-w-0 break-words">{node.name}</span>
                </Link>
              </li>
            ))}
          </ul>
          {row.nodes.length > 6 && (
            <Button
              variant="ghost"
              onClick={() => {
                setAll(!all);
              }}
            >
              {all ? t("showLess") : `+${row.nodes.length - 6}`}
            </Button>
          )}
        </div>
      </details>
    </li>
  );
}
