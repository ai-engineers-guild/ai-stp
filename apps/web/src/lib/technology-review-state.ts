"use client";
import { useId, useState } from "react";
import { useTranslations } from "next-intl";
import { displayCategoryIds, useTechnologyTaxonomy } from "@/lib/technology-taxonomy";
import {
  useGovernanceMutation,
  type GovernanceAuthority,
} from "@/components/organisms/corporate-governance-controls";
import type {
  AreaView,
  CategoryView,
  CorporateProjectView,
  TechnologyScanDetail,
  TechnologyScanFinding,
  TechnologyView,
} from "@/lib/api/generated/types.gen";
export type Row = TechnologyScanFinding & { scan: TechnologyScanDetail; members?: Row[] };
export type Draft = {
  technology: string;
  category: string;
  comment: string;
  review: "open" | "confirmed" | "rejected";
};
export function rowKey(row: Row) {
  return JSON.stringify([row.scan.scan_id, row.kind, row.coordinate, row.context]);
}
const sourceIcon = (source: string) =>
  source === "gitlab" ? "gitlab" : source === "github" ? "github" : "devices";

export function useTechnologyReview({
  scans,
  technologies,
  categories,
  areas,
  canUpdate,
  projects = [],
  mode = "scan",
  initialScan = "",
  initialDate = "",
  ...authority
}: GovernanceAuthority & {
  scans: TechnologyScanDetail[];
  technologies: TechnologyView[];
  categories: CategoryView[] | null;
  areas: AreaView[] | null;
  canUpdate: boolean;
  projects?: CorporateProjectView[];
  mode?: "scan" | "mapping";
  initialScan?: string;
  initialDate?: string;
}) {
  const t = useTranslations("technology"),
    w = useTranslations("technology.workspace"),
    s = useTranslations("technology.scans");
  const a = useTranslations("technology.areas");
  const localize = useTechnologyTaxonomy();
  const id = useId();
  const mutation = useGovernanceMutation(authority);
  const filters = useReviewFilters(initialScan, initialDate);
  const {
    search,
    project,
    scanFilter,
    status,
    kind,
    date,
    pendingOnly,
    page,
    size,
    depPage,
    depSize,
  } = filters;
  const ui = useReviewUi();
  const { activeKey, drafts, selected, setDrafts, setSelected } = ui;
  const names = new Map(technologies.map((item) => [item.technology_id, item]));
  const categoryNames = new Map(
    categories?.map((item) => [item.category_id, localize(item)]) ?? [],
  );
  const areaNames = new Map(areas?.map((item) => [item.area_id, localize(item).name]) ?? []);
  const allRows = groupFindingRows(scans);
  function draft(row: Row) {
    return drafts[rowKey(row)] ?? defaultDraft(row, names);
  }
  function patch(row: Row, value: Partial<Draft>) {
    setDrafts((current) => ({ ...current, [rowKey(row)]: { ...draft(row), ...value } }));
  }
  function pending(row: Row) {
    return !["resolved", "rejected"].includes(findingStatus(row, names));
  }
  const {
    rows,
    techRows,
    depRows,
    totalPages,
    currentPage,
    visible,
    depTotalPages,
    depCurrentPage,
    depVisible,
  } = partitionRows(
    allRows,
    {
      mode,
      scanFilter,
      latest: latestScanIds(scans),
      project,
      status,
      kind,
      date,
      pendingOnly,
      search,
      names,
      pending,
    },
    page,
    size,
    depPage,
    depSize,
  );
  const active = rows.find((row) => rowKey(row) === activeKey) ?? visible[0] ?? null;
  const chosen = active ? draft(active) : null;
  const category = chosen ? categoryNames.get(chosen.category) : undefined;
  const bulkRows = selected.length
    ? rows.filter((row) => selected.includes(rowKey(row)))
    : rows.filter((row) => drafts[rowKey(row)]);
  const applicable = bulkRows.filter((row) => canApplyFinding(draft(row), names));
  function apply(items: Row[], reject = false) {
    applyFindings(mutation, authority, items, draft, reject, () => {
      setDrafts({});
      setSelected([]);
    });
  }
  const classification = (row: Row) =>
    findingClassification(row, names, categoryNames, areaNames, a("unclassified"));
  const scan = mode === "scan" ? scans[0] : undefined;
  return {
    technologies,
    categories: categories?.map(localize) ?? null,
    areas: areas?.map(localize) ?? null,
    t,
    w,
    s,
    id,
    mutation,
    names,
    categoryNames,
    areaNames,
    allRows,
    rows,
    techRows,
    depRows,
    visible,
    depVisible,
    active,
    chosen,
    category,
    applicable,
    scan,
    canUpdate,
    authority,
    projects,
    scans,
    mode,
    totalPages,
    currentPage,
    depTotalPages,
    depCurrentPage,
    classification,
    sourceIcon,
    draft,
    patch,
    apply,
    pending,
    ...filters,
    ...ui,
  };
}
export type TechnologyReviewState = ReturnType<typeof useTechnologyReview>;

function useReviewFilters(initialScan: string, initialDate: string) {
  const [search, setSearch] = useState("");
  const [project, setProject] = useState("");
  const [scanFilter, setScanFilter] = useState(initialScan);
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");
  const [date, setDate] = useState(initialDate);
  const [pendingOnly, setPendingOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(10);
  const [depPage, setDepPage] = useState(1);
  const [depSize, setDepSize] = useState(10);
  return {
    search,
    project,
    scanFilter,
    status,
    kind,
    date,
    pendingOnly,
    page,
    size,
    depPage,
    depSize,
    setSearch,
    setProject,
    setScanFilter,
    setStatus,
    setKind,
    setDate,
    setPendingOnly,
    setPage,
    setSize,
    setDepPage,
    setDepSize,
  };
}

function useReviewUi() {
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [create, setCreate] = useState<"technology" | "category" | "area" | null>(null);
  const [evidence, setEvidence] = useState<Row | null>(null);
  return {
    activeKey,
    drafts,
    selected,
    create,
    evidence,
    setActiveKey,
    setDrafts,
    setSelected,
    setCreate,
    setEvidence,
  };
}

function pageSlice<T>(rows: T[], page: number, size: number) {
  const totalPages = Math.max(1, Math.ceil(rows.length / size));
  const current = Math.min(page, totalPages);
  return {
    totalPages,
    currentPage: current,
    visible: rows.slice((current - 1) * size, current * size),
  };
}

type RowFilters = {
  mode: "scan" | "mapping";
  scanFilter: string;
  latest: Set<string>;
  project: string;
  status: string;
  kind: string;
  date: string;
  pendingOnly: boolean;
  search: string;
  names: Map<string, TechnologyView>;
  pending: (row: Row) => boolean;
};

function partitionRows(
  allRows: Row[],
  filters: RowFilters,
  page: number,
  size: number,
  depPage: number,
  depSize: number,
) {
  const rows = allRows.filter((row) => rowMatches(row, filters));
  const techRows = rows.filter((row) => row.tier !== "dependency");
  const depRows = rows.filter((row) => row.tier === "dependency");
  const dep = pageSlice(depRows, depPage, depSize);
  return {
    rows,
    techRows,
    depRows,
    ...pageSlice(techRows, page, size),
    depTotalPages: dep.totalPages,
    depCurrentPage: dep.currentPage,
    depVisible: dep.visible,
  };
}

function rowMatches(row: Row, filters: RowFilters) {
  return (
    (!filters.scanFilter
      ? filters.mode === "scan" || filters.latest.has(row.scan.scan_id)
      : row.scan.scan_id === filters.scanFilter) &&
    (!filters.project || row.scan.project_id === filters.project) &&
    (!filters.status || findingStatus(row, filters.names) === filters.status) &&
    (!filters.kind ||
      (filters.mode === "mapping"
        ? findingReason(row, filters.names) === filters.kind
        : row.kind === filters.kind)) &&
    (!filters.date || row.scan.created_at.slice(0, 10) >= filters.date) &&
    (!filters.pendingOnly || filters.pending(row)) &&
    rowHaystack(row, filters.names).includes(filters.search.toLocaleLowerCase())
  );
}

function rowHaystack(row: Row, names: Map<string, TechnologyView>) {
  return `${row.technology_name ?? ""} ${row.coordinate} ${names.get(row.technology_id ?? row.candidate_technology_id ?? "")?.name ?? ""} ${row.scan.project_name ?? ""} ${row.evidence.map((e) => e.path ?? e.reference).join(" ")}`.toLocaleLowerCase();
}

function applyFindings(
  mutation: ReturnType<typeof useGovernanceMutation>,
  authority: GovernanceAuthority,
  items: Row[],
  decide: (row: Row) => Draft,
  reject: boolean,
  onSaved: () => void,
) {
  const decisions = items.flatMap((row) =>
    (row.members ?? [row]).map((member) => findingDecision(member, decide(row), reject)),
  );
  mutation.save(
    `/v1/corporate/organizations/${authority.organizationId}/technology-findings/review`,
    { expected_revision: 0, items: decisions },
    "PUT",
    onSaved,
  );
}

function defaultDraft(row: Row, names: Map<string, TechnologyView>): Draft {
  const technology = row.technology_id ?? row.candidate_technology_id ?? "";
  const record = names.get(technology);
  return {
    technology,
    category: row.category_id ?? (record ? (displayCategoryIds(record)[0] ?? "") : ""),
    comment: row.comment,
    review:
      row.state === "rejected" ? "rejected" : row.review === "confirmed" ? "confirmed" : "open",
  };
}
function canApplyFinding(draft: Draft, names: Map<string, TechnologyView>) {
  return (
    draft.review === "rejected" ||
    ((draft.technology || draft.category) && names.get(draft.technology)?.lifecycle !== "archived")
  );
}
function latestScanIds(scans: TechnologyScanDetail[]) {
  const latest = new Set<string>();
  const scopes = new Set<string>();
  for (const scan of scans) {
    const key = `${scan.project_id}:${scan.scope ?? scan.repository ?? ""}`;
    if (!scopes.has(key)) {
      scopes.add(key);
      latest.add(scan.scan_id);
    }
  }
  return latest;
}
function findingClassification(
  row: Row,
  names: Map<string, TechnologyView>,
  categoryNames: Map<string, CategoryView>,
  areaNames: Map<string, string>,
  unclassified: string,
) {
  const technology = names.get(row.technology_id ?? row.candidate_technology_id ?? "");
  return (
    (technology ? displayCategoryIds(technology, categoryNames) : [])
      .map((key) => {
        const c = categoryNames.get(key);
        return c ? `${areaNames.get(c.area_id ?? "") ?? unclassified} / ${c.name}` : "";
      })
      .filter(Boolean)
      .join(", ") || "—"
  );
}

function findingDecision(row: Row, value: Draft, reject: boolean) {
  return {
    scan_id: row.scan.scan_id,
    kind: row.kind,
    coordinate: row.coordinate,
    context: row.context,
    technology_id: value.technology || null,
    category_id: value.category || null,
    review: reject || value.review === "rejected" ? "rejected" : "confirmed",
    expected_revision: row.review_revision,
    comment: value.comment,
  };
}

export function findingReason(row: Row, names: Map<string, TechnologyView>) {
  if (row.state === "rejected" || row.review === "rejected") return "excluded";
  if (row.review === "confirmed") return "confirmed";
  if (row.state === "open") return "unrecognized";
  if (row.state === "candidate") return "candidate";
  if (!names.get(row.technology_id ?? "")?.category_ids.length) return "category";
  return "confirmed";
}

export function findingStatus(row: Row, names: Map<string, TechnologyView>) {
  const reason = findingReason(row, names);
  if (reason === "confirmed") return "resolved";
  if (reason === "excluded") return "rejected";
  return reason === "category" ? reason : row.state;
}

export function groupFindingRows(scans: TechnologyScanDetail[]): Row[] {
  const grouped = new Map<string, Row>();
  for (const scan of scans)
    for (const finding of scan.findings) {
      const member = { ...finding, scan };
      const key = JSON.stringify([
        scan.scan_id,
        finding.technology_id ??
          finding.candidate_technology_id ??
          finding.technology_key ?? [finding.kind, finding.coordinate],
      ]);
      const previous = grouped.get(key);
      if (!previous) {
        grouped.set(key, { ...member, members: [member] });
        continue;
      }
      const members = [...(previous.members ?? [previous])];
      const existing = members.find((item) => rowKey(item) === rowKey(member));
      if (!existing) members.push(member);
      const versions = [
        ...new Set([...(previous.version ?? "").split(", "), finding.version].filter(Boolean)),
      ];
      const evidence = [
        ...new Map(
          [...previous.evidence, ...finding.evidence].map((entry) => [
            JSON.stringify(entry),
            entry,
          ]),
        ).values(),
      ];
      grouped.set(key, { ...previous, members, evidence, version: versions.join(", ") || null });
    }
  return [...grouped.values()];
}
