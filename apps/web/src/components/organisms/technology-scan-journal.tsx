"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { Badge } from "@/components/atoms/badge";
import { Select } from "@/components/atoms/select";
import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";
import { PagePager } from "@/components/molecules/page-pager";
import { TechnologyFilterToolbar } from "@/components/organisms/technology-filter-toolbar";
import { Link, useRouter } from "@/lib/i18n/navigation";
import { EntityDetailMenu } from "@/components/organisms/entity-detail-menu";
import type { CorporateProjectView, TechnologyScanListEntry } from "@/lib/api/generated/types.gen";
import { Icon } from "@/theme";

export function TechnologyScanJournal({
  items,
  projects,
  initialProject = "",
}: {
  items: TechnologyScanListEntry[];
  projects: CorporateProjectView[];
  initialProject?: string;
}) {
  const w = useTranslations("technology.workspace"),
    s = useTranslations("technology.scans"),
    t = useTranslations("technology");
  const [search, setSearch] = useState(""),
    [project, setProject] = useState(initialProject),
    [source, setSource] = useState(""),
    [status, setStatus] = useState(""),
    [date, setDate] = useState("");
  const [page, setPage] = useState(1),
    [size, setSize] = useState(20);
  const rows = items.filter(
    (item) =>
      (!project || item.project_id === project) &&
      (!source || item.source === source) &&
      (!status || item.status === status) &&
      (!date || item.created_at.slice(0, 10) >= date) &&
      `${item.scan_id} ${item.project_name ?? ""} ${item.repository ?? ""}`
        .toLocaleLowerCase()
        .includes(search.toLocaleLowerCase()),
  );
  const totalPages = Math.max(1, Math.ceil(rows.length / size)),
    currentPage = Math.min(page, totalPages),
    visible = rows.slice((currentPage - 1) * size, currentPage * size);
  return (
    <section className="space-y-4">
      <TechnologyFilterToolbar
        search={search}
        searchPlaceholder={w("searchScans")}
        onSearchChange={(value) => {
          setSearch(value);
          setPage(1);
        }}
        facets={[
          {
            kind: "options",
            key: "project",
            label: w("project"),
            options: projects.map((p) => ({ value: p.project_id, label: p.name })),
          },
          {
            kind: "options",
            key: "source",
            label: w("source"),
            options: ["gitlab", "github", "local"].map((value) => ({
              value,
              label: s(`source.${value}`),
            })),
          },
          {
            kind: "options",
            key: "status",
            label: w("status"),
            options: ["queued", "running", "succeeded", "failed"].map((value) => ({
              value,
              label: s(`status.${value}`),
            })),
          },
          { kind: "date", key: "date", label: w("dateFrom") },
        ]}
        values={{
          project: project ? [project] : [],
          source: source ? [source] : [],
          status: status ? [status] : [],
          date,
        }}
        onApply={(values) => {
          setProject((values.project as string[])[0] ?? "");
          setSource((values.source as string[])[0] ?? "");
          setStatus((values.status as string[])[0] ?? "");
          setDate(values.date as string);
          setPage(1);
        }}
        onReset={() => {
          setProject("");
          setSource("");
          setStatus("");
          setDate("");
          setPage(1);
        }}
      />
      <TechnologyScanJournalTable items={visible} projects={projects} />
      {!visible.length && (
        <p role="status" className="text-muted-foreground p-8 text-center text-sm">
          {s("empty")}
        </p>
      )}
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
          <div className="flex items-center gap-4 text-sm">
            <span>{w("shown", { count: visible.length, total: rows.length })}</span>
            <Select
              aria-label={w("pageSize")}
              className="w-36"
              value={size}
              onChange={(e) => {
                setSize(Number(e.target.value));
                setPage(1);
              }}
            >
              {[10, 20, 50].map((value) => (
                <option key={value} value={value}>
                  {w("perPage", { count: value })}
                </option>
              ))}
            </Select>
          </div>
        }
      />
    </section>
  );
}

export function TechnologyScanJournalTable({
  items,
  projects,
}: {
  items: TechnologyScanListEntry[];
  projects: CorporateProjectView[];
}) {
  const w = useTranslations("technology.workspace"),
    s = useTranslations("technology.scans"),
    locale = useLocale();
  const h = useTranslations("hub");
  const router = useRouter();
  const scanType = useTranslations("technology.workspace.scanTypes");
  const scanTypes = {
    dependencies: scanType("dependencies"),
    configs: scanType("configs"),
    languages: scanType("languages"),
  };
  return (
    <div
      className="technology-table-frame"
      role="region"
      aria-label={s("title")}
      // The scroll region must remain keyboard accessible on narrow screens.
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
      tabIndex={0}
    >
      <Table className="technology-journal-table">
        <caption className="sr-only">{s("title")}</caption>
        <THead>
          <Tr>
            {[
              "id",
              "projectRepository",
              "source",
              "dateTime",
              "scanType",
              "status",
              "found",
              "pending",
            ].map((key) => (
              <Th key={key}>{w(key)}</Th>
            ))}
            <Th>
              <span className="sr-only">{w("actions")}</span>
            </Th>
          </Tr>
        </THead>
        <TBody>
          {items.map((scan) => (
            <Tr
              key={scan.scan_id}
              className="hover:bg-muted/50 cursor-pointer"
              tabIndex={0}
              onClick={(event) => {
                if (!(event.target as HTMLElement).closest("a,button,[role=menuitem]"))
                  router.push(`/corporate/technology-scans/${scan.scan_id}`);
              }}
              onKeyDown={(event) => {
                if (
                  event.target === event.currentTarget &&
                  (event.key === "Enter" || event.key === " ")
                ) {
                  event.preventDefault();
                  router.push(`/corporate/technology-scans/${scan.scan_id}`);
                }
              }}
            >
              <Td>
                <Link
                  className="inline-flex min-h-11 items-center text-xs"
                  href={`/corporate/technology-scans/${scan.scan_id}`}
                >
                  {scan.scan_id}
                </Link>
              </Td>
              <Td>
                <Link className="block font-medium" href={`/corporate/projects/${scan.project_id}`}>
                  {scan.project_name ??
                    projects.find((p) => p.project_id === scan.project_id)?.name ??
                    scan.project_id}
                </Link>
                <span
                  className="text-muted-foreground block max-w-80 truncate text-xs"
                  title={scan.repository ?? undefined}
                >
                  {scan.repository ?? "—"}
                </span>
              </Td>
              <Td>
                <span className="flex items-center gap-2 whitespace-nowrap">
                  <Icon
                    name={
                      scan.source === "gitlab"
                        ? "gitlab"
                        : scan.source === "github"
                          ? "github"
                          : "devices"
                    }
                  />
                  {s(`source.${scan.source}`)}
                </span>
              </Td>
              <Td className="whitespace-nowrap tabular-nums">
                {new Date(scan.created_at).toLocaleString(locale, {
                  timeZone: "UTC",
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
                <span className="text-muted-foreground block text-xs">
                  {scan.duration_seconds == null
                    ? "—"
                    : w("seconds", { count: scan.duration_seconds })}
                </span>
              </Td>
              <Td className="text-muted-foreground">
                {scan.scan_types.map((kind) => scanTypes[kind]).join(", ") || "—"}
              </Td>
              <Td>
                <Badge variant="secondary" className="whitespace-nowrap">
                  {s(`status.${scan.status}`)}
                </Badge>
              </Td>
              <Td>{scan.status === "failed" ? "—" : scan.found}</Td>
              <Td>{scan.status === "failed" ? "—" : scan.pending}</Td>
              <Td>
                <div className="flex items-center gap-2">
                  <Button asChild variant="outline" size="icon" aria-label={w("project")}>
                    <Link href={`/corporate/projects/${scan.project_id}`}>
                      <Icon name="component" />
                    </Link>
                  </Button>
                  <EntityDetailMenu
                    moreLabel={w("actions")}
                    subject={{ kind: "scan", id: scan.scan_id }}
                    choices={[
                      {
                        actionId: "open",
                        label: h("openDetails"),
                        href: `/corporate/technology-scans/${scan.scan_id}`,
                      },
                    ]}
                  />
                </div>
              </Td>
            </Tr>
          ))}
        </TBody>
      </Table>
    </div>
  );
}
