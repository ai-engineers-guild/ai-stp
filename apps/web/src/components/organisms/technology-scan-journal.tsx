"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/atoms/dialog";
import { Label } from "@/components/atoms/label";
import { Select } from "@/components/atoms/select";
import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";
import { PagePager } from "@/components/molecules/page-pager";
import { Link } from "@/lib/i18n/navigation";
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
      <div className="technology-filter-bar">
        <div className="technology-search">
          <Icon name="search" size="sm" />
          <Input
            aria-label={t("search")}
            placeholder={w("searchScans")}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <Select
          aria-label={w("project")}
          value={project}
          onChange={(e) => {
            setProject(e.target.value);
            setPage(1);
          }}
        >
          <option value="">{w("allProjects")}</option>
          {projects.map((p) => (
            <option key={p.project_id} value={p.project_id}>
              {p.name}
            </option>
          ))}
        </Select>
        <Select
          aria-label={w("source")}
          value={source}
          onChange={(e) => {
            setSource(e.target.value);
            setPage(1);
          }}
        >
          <option value="">{w("allSources")}</option>
          {["gitlab", "github", "local"].map((value) => (
            <option key={value} value={value}>
              {s(`source.${value}`)}
            </option>
          ))}
        </Select>
        <Select
          aria-label={w("status")}
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
        >
          <option value="">{w("allStatuses")}</option>
          {["queued", "running", "succeeded", "failed"].map((value) => (
            <option key={value} value={value}>
              {s(`status.${value}`)}
            </option>
          ))}
        </Select>
        <TechnologyScanDateFilter
          date={date}
          onChange={(value) => {
            setDate(value);
            setPage(1);
          }}
        />
      </div>
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
            <Tr key={scan.scan_id}>
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
                <Button asChild size="icon" variant="ghost">
                  <Link
                    href={`/corporate/technology-scans/${scan.scan_id}`}
                    aria-label={w("openScan", { id: scan.scan_id })}
                  >
                    <Icon name="more" size="sm" />
                  </Link>
                </Button>
              </Td>
            </Tr>
          ))}
        </TBody>
      </Table>
    </div>
  );
}

function TechnologyScanDateFilter({
  date,
  onChange,
}: {
  date: string;
  onChange: (date: string) => void;
}) {
  const w = useTranslations("technology.workspace"),
    t = useTranslations("technology");
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" className="justify-start">
          <Icon name="calendar" size="sm" />
          {date || w("allTime")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>{w("dateFrom")}</DialogTitle>
        <DialogDescription>{w("dateDescription")}</DialogDescription>
        <Label htmlFor="technology-journal-date">{w("dateFrom")}</Label>
        <Input
          id="technology-journal-date"
          type="date"
          value={date}
          onChange={(e) => {
            onChange(e.target.value);
          }}
        />
        <Button
          variant="outline"
          onClick={() => {
            onChange("");
          }}
        >
          {t("reset")}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
