"use client";

import { useTranslations } from "next-intl";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";

import { Select } from "@/components/atoms/select";

import { TechnologyScanLaunch } from "@/components/organisms/technology-scan-launch";

import { Link } from "@/lib/i18n/navigation";

import { Icon } from "@/theme";

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
            [w("found"), scan.found],
            [w("pending"), scan.pending],
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
    t,
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
    pending,
    setSearch,
    setProject,
    setScanFilter,
    setStatus,
    setKind,
    setPage,
    setAdvanced,
  } = state;
  return (
    <>
      {mode === "mapping" && (
        <div className="technology-filter-bar">
          <div className="technology-search">
            <Icon name="search" size="sm" />
            <Input
              aria-label={t("search")}
              placeholder={w("searchMapping")}
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
            aria-label={w("scan")}
            value={scanFilter}
            onChange={(e) => {
              setScanFilter(e.target.value);
              setPage(1);
            }}
          >
            <option value="">{w("allCurrentScans")}</option>
            {scans.map((item) => (
              <option key={item.scan_id} value={item.scan_id}>
                {item.scan_id}
              </option>
            ))}
          </Select>
          <Select
            aria-label={w("reason")}
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setPage(1);
            }}
          >
            <option value="">{w("allReasons")}</option>
            {[...new Set(allRows.map((r) => findingReason(r, names)))].map((value) => (
              <option key={value} value={value}>
                {w(`reasonState.${value}`)}
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
            {["open", "candidate", "confirmation", "category", "resolved", "rejected"].map(
              (value) => (
                <option key={value} value={value}>
                  {w(`findingState.${value}`)}
                </option>
              ),
            )}
          </Select>
          <Button
            variant="outline"
            onClick={() => {
              setAdvanced(true);
            }}
          >
            <Icon name="filter" size="sm" />
            {t("filters")}
          </Button>
        </div>
      )}
      {mode === "mapping" && (
        <p className="text-sm">
          {w("findingSummary", {
            total: rows.length,
            pending: rows.filter(pending).length,
            resolved: rows.filter((r) => r.review === "confirmed").length,
          })}
        </p>
      )}
    </>
  );
}
