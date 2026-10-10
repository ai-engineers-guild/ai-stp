"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/atoms/dialog";
import { Label } from "@/components/atoms/label";
import { Select } from "@/components/atoms/select";

import { TechnologyFilterToolbar } from "@/components/organisms/technology-filter-toolbar";

import { Link, usePathname, useRouter } from "@/lib/i18n/navigation";

import { Icon } from "@/theme";

import {
  downloadScanFindings,
  type FindingExportFormat,
  type FindingExportScope,
} from "@/lib/findings-export";
import { findingReason, type TechnologyReviewState } from "@/lib/technology-review-state";
export function TechnologyReviewHeader({ state }: { state: TechnologyReviewState }) {
  const { t, w, mutation, applicable, scan, canUpdate, mode, selected, apply, setCreate } = state;
  return (
    <>
      <div className="technology-page-actions">
        <Link
          href={scan ? "/corporate/technology-scans" : "/corporate/technology-landscape"}
          className="inline-flex min-h-11 items-center gap-2 text-sm font-medium"
        >
          <Icon name="arrowLeft" size="sm" />
          {w(scan ? "backScans" : "backLandscape")}
        </Link>
        <div className="flex flex-wrap gap-3">
          {canUpdate && (
            <Button
              variant="outline"
              onClick={() => {
                setCreate("technology");
              }}
            >
              <Icon name="plus" size="sm" />
              {w("createTechnology")}
            </Button>
          )}
          {canUpdate && mode === "mapping" && (
            <Button
              disabled={mutation.busy || !applicable.length}
              onClick={() => {
                apply(applicable);
              }}
            >
              <Icon name="play" size="sm" />
              {w("publish")}
              {selected.length ? ` (${selected.length})` : ""}
            </Button>
          )}
          {scan && <TechnologyScanExport state={state} />}
        </div>
      </div>
      <header className="space-y-2">
        <h1>{scan ? w("scanTitle", { id: scan.scan_id }) : t("mappingTitle")}</h1>
        <p className="text-muted-foreground text-sm">
          {w(scan ? "scanDescription" : "mappingDescription")}
        </p>
      </header>
    </>
  );
}
function TechnologyScanExport({ state }: { state: TechnologyReviewState }) {
  const { w, scan } = state;
  const [open, setOpen] = useState(false);
  const [scope, setScope] = useState<FindingExportScope>("both");
  const [format, setFormat] = useState<FindingExportFormat>("md");
  if (!scan) return null;
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" aria-label={w("downloadFindings")}>
          <Icon name="download" size="sm" />
          {w("downloadFindings")}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogTitle>{w("downloadFindings")}</DialogTitle>
        <DialogDescription>{w("exportDescription")}</DialogDescription>
        <div className="space-y-2">
          <Label htmlFor="export-scope">{w("exportScope")}</Label>
          <Select
            id="export-scope"
            value={scope}
            onChange={(e) => {
              setScope(e.target.value as FindingExportScope);
            }}
          >
            {(["technologies", "findings", "both"] as const).map((value) => (
              <option key={value} value={value}>
                {w(`exportScopes.${value}`)}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="export-format">{w("exportFormat")}</Label>
          <Select
            id="export-format"
            value={format}
            onChange={(e) => {
              setFormat(e.target.value as FindingExportFormat);
            }}
          >
            {(["md", "csv", "json"] as const).map((value) => (
              <option key={value} value={value}>
                {w(`exportFormats.${value}`)}
              </option>
            ))}
          </Select>
        </div>
        <Button
          onClick={() => {
            downloadScanFindings(scan, format, scope);
            setOpen(false);
          }}
        >
          {w("downloadFindings")}
        </Button>
      </DialogContent>
    </Dialog>
  );
}

export function TechnologyScanMetadata({ state }: { state: TechnologyReviewState }) {
  const { w, s, scan, sourceIcon } = state;
  const scanType = useTranslations("technology.workspace.scanTypes");
  const scanTypes = {
    dependencies: scanType("dependencies"),
    configs: scanType("configs"),
    languages: scanType("languages"),
  };
  return (
    <>
      {scan && (
        <dl className="technology-scan-metadata">
          {[
            [w("project"), scan.project_name ?? scan.project_id],
            [w("repository"), scan.repository ?? "—"],
            [
              w("source"),
              <span key="source" className="flex items-center gap-2">
                <Icon name={sourceIcon(scan.source)} size="sm" />
                {s(`source.${scan.source}`)}
              </span>,
            ],
            [w("branch"), scan.branch ?? "—"],
            [w("commit"), scan.commit?.slice(0, 8) ?? "—"],
            [w("scanType"), scan.scan_types.map((kind) => scanTypes[kind]).join(", ") || "—"],
            [
              w("status"),
              <Badge key="status" variant="secondary">
                {s(`status.${scan.status}`)}
              </Badge>,
            ],
            [
              w("duration"),
              scan.duration_seconds == null ? "—" : w("seconds", { count: scan.duration_seconds }),
            ],
            [w("found"), state.allRows.filter((row) => row.tier !== "dependency").length],
            [w("pending"), state.allRows.filter(state.pending).length],
          ].map(([label, value], index) => (
            <div key={index}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {scan?.error && (
        <p role="alert" className="border-destructive rounded-sm border p-3 text-sm">
          {w("scanFailed")}
        </p>
      )}
    </>
  );
}
export function TechnologyReviewFilters({ state }: { state: TechnologyReviewState }) {
  const {
    w,
    allRows,
    names,
    rows,
    projects,
    scans,
    mode,
    search,
    project,
    scanFilter,
    status,
    kind,
    date,
    pendingOnly,
    pending,
    setSearch,
    setProject,
    setScanFilter,
    setStatus,
    setKind,
    setDate,
    setPendingOnly,
    setPage,
  } = state;
  const router = useRouter();
  const pathname = usePathname();
  if (mode !== "mapping") return null;
  return (
    <>
      <TechnologyFilterToolbar
        search={search}
        searchPlaceholder={w("searchMapping")}
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
            key: "scan",
            label: w("scan"),
            options: scans.map((item) => ({ value: item.scan_id, label: item.scan_id })),
          },
          {
            kind: "options",
            key: "reason",
            label: w("reason"),
            options: [...new Set(allRows.map((r) => findingReason(r, names)))].map((value) => ({
              value,
              label: w(`reasonState.${value}`),
            })),
          },
          {
            kind: "options",
            key: "status",
            label: w("status"),
            options: ["open", "candidate", "confirmation", "category", "resolved", "rejected"].map(
              (value) => ({ value, label: w(`findingState.${value}`) }),
            ),
          },
          { kind: "date", key: "date", label: w("dateFrom") },
          { kind: "flag", key: "pending", label: w("pendingOnly") },
        ]}
        values={{
          project: project ? [project] : [],
          scan: scanFilter ? [scanFilter] : [],
          reason: kind ? [kind] : [],
          status: status ? [status] : [],
          date,
          pending: pendingOnly,
        }}
        onApply={(values) => {
          setProject((values.project as string[])[0] ?? "");
          setScanFilter((values.scan as string[])[0] ?? "");
          setKind((values.reason as string[])[0] ?? "");
          setStatus((values.status as string[])[0] ?? "");
          setDate(values.date as string);
          setPendingOnly(Boolean(values.pending));
          setPage(1);
          const nextDate = (values.date as string) || "";
          const params = new URLSearchParams(window.location.search);
          if (nextDate) params.set("scan_from", nextDate);
          else params.delete("scan_from");
          router.replace(`${pathname}${params.size ? `?${params.toString()}` : ""}`, {
            scroll: false,
          });
        }}
        onReset={() => {
          setProject("");
          setScanFilter("");
          setKind("");
          setStatus("");
          setDate("");
          setPendingOnly(false);
          setPage(1);
        }}
      />
      <p className="text-sm">
        {w("findingSummary", {
          total: rows.length,
          pending: rows.filter(pending).length,
          resolved: rows.filter((r) => r.review === "confirmed").length,
        })}
      </p>
    </>
  );
}
