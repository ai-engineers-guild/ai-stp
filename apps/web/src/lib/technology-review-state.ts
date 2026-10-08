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
export type Row = TechnologyScanFinding & { scan: TechnologyScanDetail };
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
}) {
  const t = useTranslations("technology"),
    w = useTranslations("technology.workspace"),
    s = useTranslations("technology.scans");
  const a = useTranslations("technology.areas");
  const localize = useTechnologyTaxonomy();
  const id = useId();
  const mutation = useGovernanceMutation(authority);
  const [search, setSearch] = useState("");
  const [project, setProject] = useState("");
  const [scanFilter, setScanFilter] = useState(initialScan);
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");
  const [pendingOnly, setPendingOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(10);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [create, setCreate] = useState<"technology" | "category" | "area" | null>(null);
  const [evidence, setEvidence] = useState<Row | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const names = new Map(technologies.map((item) => [item.technology_id, item]));
  const categoryNames = new Map(
    categories?.map((item) => [item.category_id, localize(item)]) ?? [],
  );
  const areaNames = new Map(areas?.map((item) => [item.area_id, localize(item).name]) ?? []);
  const allRows: Row[] = scans.flatMap((scan) =>
    scan.findings.map((finding) => ({ ...finding, scan })),
  );
  function draft(row: Row) {
    return drafts[rowKey(row)] ?? defaultDraft(row, names);
  }
  function patch(row: Row, value: Partial<Draft>) {
    setDrafts((current) => ({ ...current, [rowKey(row)]: { ...draft(row), ...value } }));
  }
  function pending(row: Row) {
    return row.state !== "rejected" && row.review !== "confirmed";
  }
  const latest = latestScanIds(scans);
  const rows = allRows.filter(
    (row) =>
      (!scanFilter
        ? mode === "scan" || latest.has(row.scan.scan_id)
        : row.scan.scan_id === scanFilter) &&
      (!project || row.scan.project_id === project) &&
      (!status || findingStatus(row, names) === status) &&
      (!kind || (mode === "mapping" ? findingReason(row, names) === kind : row.kind === kind)) &&
      (!pendingOnly || pending(row)) &&
      `${row.coordinate} ${names.get(row.technology_id ?? row.candidate_technology_id ?? "")?.name ?? ""} ${row.scan.project_name ?? ""} ${row.evidence.map((e) => e.path ?? e.reference).join(" ")}`
        .toLocaleLowerCase()
        .includes(search.toLocaleLowerCase()),
  );
  const totalPages = Math.max(1, Math.ceil(rows.length / size));
  const currentPage = Math.min(page, totalPages);
  const visible = rows.slice((currentPage - 1) * size, currentPage * size);
  const active = rows.find((row) => rowKey(row) === activeKey) ?? visible[0] ?? null;
  const chosen = active ? draft(active) : null;
  const category = chosen ? categoryNames.get(chosen.category) : undefined;
  const bulkRows = selected.length
    ? rows.filter((row) => selected.includes(rowKey(row)))
    : rows.filter((row) => drafts[rowKey(row)] || pending(row));
  const applicable = bulkRows.filter((row) => canApplyFinding(draft(row), names));
  function apply(items: Row[], reject = false) {
    const decisions = items.map((row) => findingDecision(row, draft(row), reject));
    mutation.save(
      `/v1/corporate/organizations/${authority.organizationId}/technology-findings/review`,
      { expected_revision: 0, items: decisions },
      "PUT",
      () => {
        setDrafts({});
        setSelected([]);
      },
    );
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
    visible,
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
    selected,
    search,
    project,
    scanFilter,
    status,
    kind,
    pendingOnly,
    page,
    size,
    totalPages,
    currentPage,
    drafts,
    create,
    evidence,
    advanced,
    classification,
    sourceIcon,
    draft,
    patch,
    apply,
    pending,
    setSearch,
    setProject,
    setScanFilter,
    setStatus,
    setKind,
    setPendingOnly,
    setPage,
    setSize,
    setActiveKey,
    setDrafts,
    setSelected,
    setCreate,
    setEvidence,
    setAdvanced,
  };
}
export type TechnologyReviewState = ReturnType<typeof useTechnologyReview>;

function defaultDraft(row: Row, names: Map<string, TechnologyView>): Draft {
  const technology = row.technology_id ?? row.candidate_technology_id ?? "";
  const record = names.get(technology);
  return {
    technology,
    category: record ? (displayCategoryIds(record)[0] ?? "") : "",
    comment: row.comment,
    review:
      row.state === "rejected" ? "rejected" : row.review === "confirmed" ? "confirmed" : "open",
  };
}
function canApplyFinding(draft: Draft, names: Map<string, TechnologyView>) {
  return (
    draft.review === "rejected" ||
    (draft.technology && names.get(draft.technology)?.lifecycle !== "archived")
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
  return "confirmation";
}

export function findingStatus(row: Row, names: Map<string, TechnologyView>) {
  const reason = findingReason(row, names);
  if (reason === "confirmed") return "resolved";
  if (reason === "excluded") return "rejected";
  return reason === "confirmation" || reason === "category" ? reason : row.state;
}
