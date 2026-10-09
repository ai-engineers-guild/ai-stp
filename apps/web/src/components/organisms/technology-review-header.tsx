"use client";

import { useTranslations } from "next-intl";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/atoms/menu";

import { TechnologyFilterToolbar } from "@/components/organisms/technology-filter-toolbar";
import { TechnologyScanLaunch } from "@/components/organisms/technology-scan-launch";

import { Link, usePathname, useRouter } from "@/lib/i18n/navigation";

import { Icon } from "@/theme";

import { downloadScanFindings } from "@/lib/findings-export";
import { findingReason, type TechnologyReviewState } from "@/lib/technology-review-state";
export function TechnologyReviewHeader({ state }: { state: TechnologyReviewState }) {
  const {
    t,
    w,
    mutation,
    applicable,
    scan,
    canUpdate,
    authority,
    projects,
    mode,
    selected,
    apply,
    setCreate,
  } = state;
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
          {canUpdate &&
            (mode === "mapping" ? (
              <Button
                variant="outline"
                onClick={() => {
                  setCreate("technology");
                }}
              >
                <Icon name="plus" size="sm" />
                {w("createTechnology")}
              </Button>
            ) : (
              <TechnologyScanLaunch
                {...authority}
                projects={projects.filter((p) => p.project_id === scan?.project_id)}
                variant="outline"
                label={w("rerunScan")}
              />
            ))}
          {canUpdate && (
            <Button
              disabled={mutation.busy || !applicable.length}
              onClick={() => {
                apply(applicable);
              }}
            >
              <Icon name="play" size="sm" />
              {w(mode === "mapping" ? "publish" : "applyChanges")}
              {selected.length ? ` (${selected.length})` : ""}
            </Button>
          )}
          {scan && (
            <Menu>
              <MenuTrigger asChild>
                <Button variant="outline" aria-label={w("downloadFindings")}>
                  <Icon name="download" size="sm" />
                  {w("downloadFindings")}
                </Button>
              </MenuTrigger>
              <MenuContent>
                <MenuItem
                  onSelect={() => {
                    downloadScanFindings(scan, "json");
                  }}
                >
                  {w("downloadJson")}
                </MenuItem>
                <MenuItem
                  onSelect={() => {
                    downloadScanFindings(scan, "csv");
                  }}
                >
                  {w("downloadCsv")}
                </MenuItem>
                <MenuItem
                  onSelect={() => {
                    downloadScanFindings(scan, "md");
                  }}
                >
                  {w("downloadMarkdown")}
                </MenuItem>
              </MenuContent>
            </Menu>
          )}
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
            [w("found"), state.allRows.length],
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
