import { describe, expect, it, vi } from "vitest";

import {
  downloadScanFindings,
  exportScanFindings,
  FINDING_EXPORT_FORMATS,
} from "@/lib/findings-export";
import { scan } from "@/mocks/technology-workspace-fixture";
import type { TechnologyScanFinding } from "@/lib/api/generated/types.gen";

const finding = (overrides: Partial<TechnologyScanFinding>): TechnologyScanFinding => ({
  ...scan.findings[1],
  ...overrides,
});

describe("exportScanFindings", () => {
  it("supports json, csv and markdown", () => {
    expect(FINDING_EXPORT_FORMATS).toEqual(["csv", "md", "json"]);
    for (const format of FINDING_EXPORT_FORMATS) {
      const result = exportScanFindings(scan, format);
      expect(result.filename).toBe(`technology-findings-${scan.scan_id}.${format}`);
      expect(result.content.length).toBeGreaterThan(0);
    }
  });

  it("serializes JSON with scan metadata and the full finding rows", () => {
    const { content, mime } = exportScanFindings(scan, "json");
    expect(mime).toBe("application/json");
    const parsed = JSON.parse(content) as {
      scan_id: string;
      repository: string;
      findings: Array<{ coordinate: string }>;
    };
    expect(parsed.scan_id).toBe(scan.scan_id);
    expect(parsed.repository).toBe(scan.repository);
    expect(parsed.findings.map((row) => row.coordinate)).toEqual([
      "fastapi",
      "weirdlib",
      "left-pad",
    ]);
  });

  it("renders CSV with the shared column set and quoting", () => {
    const { content, mime } = exportScanFindings(
      {
        ...scan,
        findings: [
          {
            ...scan.findings[0],
            coordinate: 'lib,"x"',
            evidence: [
              {
                source: "declared",
                path: "package.json",
                reference: "deps",
                observed_at: "2026-10-08T10:00:00Z",
              },
            ],
          },
        ],
      },
      "csv",
    );
    expect(mime).toBe("text/csv");
    const lines = content.split("\r\n");
    expect(lines[0]).toBe(
      "kind,tier,coordinate,technology,context,version,version_kind,state,review,evidence",
    );
    expect(lines[1]).toContain('"lib,""x"""');
    expect(lines[1]).toContain("package.json");
  });

  it("renders Markdown with scan metadata and one row per finding", () => {
    const { content, mime } = exportScanFindings(scan, "md");
    expect(mime).toBe("text/markdown");
    expect(content).toContain(`# Technology scan \`${scan.scan_id}\``);
    expect(content).toContain(`- Repository: ${scan.repository}`);
    expect(content).toContain("| package | technology | fastapi |");
    expect(content).toContain("| package | dependency | left-pad |");
    expect(content).toContain("requirements.txt");
  });

  it("defuses spreadsheet formulas and falls back through technology names", () => {
    const { content } = exportScanFindings(
      {
        ...scan,
        findings: [
          finding({ coordinate: "=DROP", technology_name: "Named" }),
          finding({ technology_name: null, technology_id: "technology_01" }),
          finding({
            technology_name: null,
            technology_id: null,
            candidate_technology_id: "technology_02",
          }),
          finding({
            technology_name: null,
            technology_id: null,
            candidate_technology_id: null,
            context: null,
            version: null,
            evidence: [
              {
                source: "observed",
                path: null,
                reference: "dockerfile:3",
                observed_at: "2026-10-08T10:00:00Z",
              },
            ],
          }),
        ],
      },
      "csv",
    );
    const lines = content.split("\r\n");
    expect(lines[1]).toContain("'=DROP");
    expect(lines[1]).toContain(",Named,");
    expect(lines[2]).toContain(",technology_01,");
    expect(lines[3]).toContain(",technology_02,");
    expect(lines[4]).toContain(",,,,declared_range,");
    expect(lines[4]).toContain("dockerfile:3");
  });

  it("escapes Markdown cells and renders absent metadata as dashes", () => {
    const { content } = exportScanFindings(
      {
        ...scan,
        repository: null,
        branch: null,
        commit: null,
        complete: false,
        detector_version: null,
        mapping_version: null,
        findings: [finding({ coordinate: "a|b\nc" })],
      },
      "md",
    );
    expect(content).toContain("- Repository: —");
    expect(content).toContain("- Detector: —");
    expect(content).toContain("- Complete: no");
    expect(content).toContain("a\\|b c");
  });

  it("downloads through a blob URL with a BOM for spreadsheet readers", () => {
    let captured: Blob | undefined;
    const create = vi.fn((blob: Blob) => {
      captured = blob;
      return "blob:fixture";
    });
    const revoke = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL: create, revokeObjectURL: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    try {
      downloadScanFindings(scan, "csv");
      expect(create).toHaveBeenCalledTimes(1);
      expect(captured?.type).toBe("text/csv;charset=utf-8");
      expect(click).toHaveBeenCalledTimes(1);
      expect(revoke).toHaveBeenCalledWith("blob:fixture");
    } finally {
      vi.unstubAllGlobals();
      click.mockRestore();
    }
  });
});
