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
    <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-card">
      {rows.map((row) => (
        <ComponentUsageRow
          key={`${row.assignment.stable_id}:${expandAll ? "open" : "closed"}`}
          row={row}
          expandAll={expandAll}
        />
      ))}
    </ul>
  ) : (
    <p role="status" className="rounded-lg border border-border p-6 text-muted-foreground">
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
        <summary className="flex cursor-pointer list-none flex-wrap items-start gap-4 p-4 hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
          <span className="grid size-11 shrink-0 place-items-center rounded-md border border-border bg-muted">
            <Icon name={icons[row.assignment.object_kind] ?? "objects"} />
          </span>
          <div className="min-w-0 flex-1">
            <Link
              href={assignmentHref(row.assignment)}
              className="font-medium break-words hover:text-primary hover:underline"
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
              <p className="mt-1 text-xs text-muted-foreground">{row.assignment.description}</p>
            )}
          </div>
          <div className="w-full text-sm text-muted-foreground sm:w-auto">
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
        <div className="mx-4 mb-4 space-y-3 rounded-md bg-muted/30 p-3">
          <div className="flex flex-wrap gap-2">
            {row.versions.map((item) => (
              <Link
                key={item.version}
                href={assignmentHref(item)}
                className="rounded-md border border-border bg-background/40 px-2 py-1 text-xs transition-colors hover:border-primary hover:bg-muted hover:text-primary"
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
                  className="flex min-h-11 min-w-0 items-center gap-2 rounded-sm border border-border px-3 py-2 text-sm transition-colors hover:border-primary hover:bg-muted hover:text-primary"
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
