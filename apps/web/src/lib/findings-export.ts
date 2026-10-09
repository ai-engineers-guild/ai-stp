/**
 * Serializes one technology scan's curated findings for download.
 *
 * Columns mirror `export_findings_csv` / `export_findings_markdown` in the
 * platform package so the client-side file and the API export read the same.
 */

import type { TechnologyScanDetail, TechnologyScanFinding } from "@/lib/api/generated/types.gen";

export type FindingExportFormat = "csv" | "md" | "json";

export const FINDING_EXPORT_FORMATS: readonly FindingExportFormat[] = [
  "csv",
  "md",
  "json",
] as const;

const MIME: Record<FindingExportFormat, string> = {
  csv: "text/csv",
  md: "text/markdown",
  json: "application/json",
};

const csvCell = (value: string) => {
  const safe = /^[\s]*[=+@-]/.test(value) ? `'${value}` : value;
  return /[",\r\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
};

const mdCell = (value: string) => value.replace(/\|/g, "\\|").replace(/[\r\n]+/g, " ");

const findingTechnology = (row: TechnologyScanFinding) =>
  row.technology_name ?? row.technology_id ?? row.candidate_technology_id ?? "";

const findingEvidence = (row: TechnologyScanFinding) =>
  row.evidence
    .map((entry) => entry.path ?? entry.reference ?? "")
    .filter(Boolean)
    .join("; ");

const findingCells = (row: TechnologyScanFinding) =>
  [
    row.kind,
    row.tier,
    row.coordinate,
    findingTechnology(row),
    row.context ?? "",
    row.version ?? "",
    row.version_kind,
    row.state,
    row.review,
    findingEvidence(row),
  ] as const;

export function exportScanFindings(
  scan: TechnologyScanDetail,
  format: FindingExportFormat,
): { filename: string; mime: string; content: string } {
  const filename = `technology-findings-${scan.scan_id}.${format}`;
  const mime = MIME[format];
  switch (format) {
    case "json":
      return {
        filename,
        mime,
        content: `${JSON.stringify(
          {
            scan_id: scan.scan_id,
            project_id: scan.project_id,
            project_name: scan.project_name,
            repository: scan.repository,
            branch: scan.branch,
            commit: scan.commit,
            created_at: scan.created_at,
            source: scan.source,
            complete: scan.complete,
            detector_version: scan.detector_version,
            mapping_version: scan.mapping_version,
            findings: scan.findings,
          },
          null,
          2,
        )}\n`,
      };
    case "csv":
      return {
        filename,
        mime,
        content: [
          "kind,tier,coordinate,technology,context,version,version_kind,state,review,evidence",
          ...scan.findings.map((row) => findingCells(row).map(csvCell).join(",")),
        ].join("\r\n"),
      };
    case "md":
      return {
        filename,
        mime,
        content: [
          `# Technology scan \`${scan.scan_id}\``,
          "",
          `- Repository: ${scan.repository ?? "—"}`,
          `- Branch: ${scan.branch ?? "—"}`,
          `- Commit: ${scan.commit ?? "—"}`,
          `- Complete: ${scan.complete ? "yes" : "no"}`,
          `- Detector: ${scan.detector_version ?? "—"}`,
          `- Mapping: ${scan.mapping_version ?? "—"}`,
          "",
          "| Kind | Tier | Coordinate | Technology | Context | Version | Version kind | State | Review | Evidence |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
          ...scan.findings.map((row) => `| ${findingCells(row).map(mdCell).join(" | ")} |`),
        ].join("\n"),
      };
  }
}

export function downloadScanFindings(
  scan: TechnologyScanDetail,
  format: FindingExportFormat,
): void {
  const { filename, mime, content } = exportScanFindings(scan, format);
  const url = URL.createObjectURL(
    new Blob([format === "csv" ? "\uFEFF" + content : content], {
      type: `${mime};charset=utf-8`,
    }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 1000);
}
