import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { SEED_A3_AGENT_ID } from "@/mocks/fixtures/catalog-ids";
import { machineDocumentToText } from "@/lib/projection/document-text";
import {
  componentFactsFromLoaders,
  componentPublicFacts,
  machineTextLeaks,
} from "@/lib/projection/page-facts";
import {
  isMachinePagePath,
  pairedPath,
  pathWithoutLocale,
  projectionSwitchHrefs,
} from "@/lib/projection/paths";
import { presentComponentDetail, presentComponentVersion } from "@/lib/projection/presenters";
import { matchesPattern } from "@/lib/projection/route-table";
import { parseProjectionRoute } from "@/lib/projection/route";

const LABELS = {
  yes: "Yes",
  no: "No",
  stableId: "stable_id",
  version: "version",
  digest: "digest",
  harness: "harness",
  trustLane: "trust_lane",
  authorVerified: "author_verified",
  componentVerified: "component_verified",
  install: "install",
  type: "component_type",
  projectionKind: "projection_kind",
  dependencies: "dependencies",
  none: "none",
};

const DEPENDENCY_ID = "component_01JQZK7B8N4M6P2R9T5V0X3YB0";

function loadedFacts() {
  return componentFactsFromLoaders({
    summary: {
      stable_id: SEED_A3_AGENT_ID,
      publisher_id: "account_01JQZK7B8N4M6P2R9T5V0X3Y70",
      latest_name: "river-planner-agent",
      latest_description: "Planning subagent for Pi documentation projects.",
      latest_version: "1.0",
      latest_harness_id: "pi",
      latest_component_type: "agent",
      latest_lifecycle: "active",
      latest_tags: ["planning", "documentation"],
      latest_trust: {
        trust_lane: "experimental",
        author_verified: false,
        component_verified: false,
      },
      latest_projection_kind: "native_files",
      latest_published_at: "2026-01-01T00:00:00Z",
    },
    digest: "sha256:" + "ab".repeat(32),
    relations: { countryCodes: ["KZ"], services: ["kaspi.kz"] },
    passport: {
      projection_kind: "native_files",
      license: { spdx_id: "AGPL-3.0-or-later" },
      requires_credentials: false,
      requires_authorization: "none",
      required_env: [{ name: "PI_TOKEN", purpose: "Pi API access" }],
      requires_components: [{ stable_id: DEPENDENCY_ID, version: "1.0" }],
      requires_capabilities: ["plan"],
      compatibility_evidence_refs: ["evidence_pi_1"],
    },
    publishedAt: "2026-01-01T00:00:00Z",
    versions: ["1.0"],
    sourceUrl: "https://github.com/ai-stp-examples/river-planner-agent",
    github: { stars: 2, archived: false },
    checks: { passed: 6, total_countable: 7, status: "available" },
  });
}

describe("component machine document completeness (REQ-3610, REQ-3623)", () => {
  it("maps the same loaders as the human page onto required public fields", () => {
    const facts = loadedFacts();
    expect(facts.stableId).toBe(SEED_A3_AGENT_ID);
    expect(facts.version).toBe("1.0");
    expect(facts.digest).toMatch(/^sha256:/);
    expect(facts.componentType).toBe("agent");
    expect(facts.projectionKind).toBe("native_files");
    expect(facts.harness).toBe("pi");
    expect(facts.trustLane).toBe("experimental");
    expect(facts.authorVerified).toBe(false);
    expect(facts.componentVerified).toBe(false);
    expect(facts.dependencies).toEqual([{ stableId: DEPENDENCY_ID, version: "1.0" }]);
    expect(facts.install).toContain(SEED_A3_AGENT_ID);
    expect(facts.install).toContain("--version 1.0");
    expect(facts.license).toBe("AGPL-3.0-or-later");
    expect(facts.requiresAuthorization).toBe("none");
  });

  it("presents every public human fact and no media or private classes", () => {
    const facts = loadedFacts();
    const text = machineDocumentToText(presentComponentDetail({ facts, labels: LABELS }), "en");
    expect(text).toContain(`stable_id: ${SEED_A3_AGENT_ID}`);
    expect(text).toContain("version: 1.0");
    expect(text).toContain(`digest: ${facts.digest}`);
    expect(text).toContain("component_type: agent");
    expect(text).toContain("projection_kind: native_files");
    expect(text).toContain("harness: pi");
    expect(text).toContain("trust_lane: experimental");
    expect(text).toContain("author_verified: No");
    expect(text).toContain("component_verified: No");
    expect(text).toContain(`dependencies: ${DEPENDENCY_ID}@1.0`);
    expect(text).toContain(facts.install);
    expect(text).toContain("license: AGPL-3.0-or-later");
    expect(text).toContain("requires_credentials: No");
    expect(text).toContain("requires_authorization: none");
    expect(text).toContain("PI_TOKEN");
    expect(text).toContain("safety_checks: 6 / 7 available");
    expect(text).not.toMatch(/catalog-art|media_|avatar|csrf|youtube/i);
    expect(machineTextLeaks(text)).toBe(false);
  });

  it("presents the version page from the same facts helper", () => {
    const facts = loadedFacts();
    const text = machineDocumentToText(presentComponentVersion({ facts, labels: LABELS }), "en");
    expect(text).toContain(`](/en/ai/catalog/components/${SEED_A3_AGENT_ID})`);
    expect(text).toContain("projection_kind: native_files");
    expect(text).toContain(`dependencies: ${DEPENDENCY_ID}@1.0`);
    expect(text).toContain("component_type: agent");
  });

  it("still builds facts when only the summary loader succeeded", () => {
    const facts = componentPublicFacts(
      {
        stable_id: SEED_A3_AGENT_ID,
        publisher_id: "account_01H",
        latest_name: "river-planner-agent",
        latest_description: "Planning subagent",
        latest_version: "1.0",
        latest_harness_id: "pi",
        latest_component_type: "agent",
        latest_lifecycle: "active",
        latest_tags: [],
        latest_trust: {
          trust_lane: "authoritative",
          author_verified: true,
          component_verified: true,
        },
        latest_projection_kind: "native_files",
      },
      "sha256:abc",
    );
    expect(facts.projectionKind).toBe("native_files");
    expect(facts.dependencies).toEqual([]);
    const text = machineDocumentToText(presentComponentDetail({ facts, labels: LABELS }), "en");
    expect(text).toContain("dependencies: none");
    expect(text).toContain("projection_kind: native_files");
  });
});

describe("component projection switch pairing (REQ-3604, REQ-3624)", () => {
  const versionPath = `/catalog/components/${SEED_A3_AGENT_ID}/versions/1.0`;

  it("never pairs a component or version page to the catalog index", () => {
    for (const path of [
      `/catalog/components/${SEED_A3_AGENT_ID}`,
      `/ai/catalog/components/${SEED_A3_AGENT_ID}`,
      `/en/catalog/components/${SEED_A3_AGENT_ID}`,
      `/en/ai/catalog/components/${SEED_A3_AGENT_ID}`,
      versionPath,
      `/en/ai${versionPath}`,
    ]) {
      const hrefs = projectionSwitchHrefs(path, "en", "?include_experimental=1");
      expect(hrefs.humanHref).toBe(
        path.includes("/versions/")
          ? `/en${versionPath}?include_experimental=1`
          : `/en/catalog/components/${SEED_A3_AGENT_ID}?include_experimental=1`,
      );
      expect(hrefs.machineHref).toBe(
        path.includes("/versions/")
          ? `/en/ai${versionPath}?include_experimental=1`
          : `/en/ai/catalog/components/${SEED_A3_AGENT_ID}?include_experimental=1`,
      );
      expect(hrefs.humanHref).not.toMatch(/\/catalog(?:\?|$)/);
      expect(hrefs.machineHref).not.toMatch(/\/ai\/catalog(?:\?|$)/);
    }
  });

  it("round-trips locale, query and version through the layout pairing pipeline", () => {
    const machine = `/ru/ai/catalog/components/${SEED_A3_AGENT_ID}/versions/1.0`;
    const parsed = parseProjectionRoute(machine);
    const pagePath = pathWithoutLocale(parsed.canonicalPathname, parsed.locale);
    const hrefs = projectionSwitchHrefs(pagePath, parsed.locale, "?q=hook");
    expect(parsed.canonicalPathname).toBe(
      `/ru/catalog/components/${SEED_A3_AGENT_ID}/versions/1.0`,
    );
    expect(hrefs.humanHref).toBe(`/ru/catalog/components/${SEED_A3_AGENT_ID}/versions/1.0?q=hook`);
    expect(hrefs.machineHref).toBe(`${machine}?q=hook`);
    expect(pairedPath(pagePath, "human", "ru")).not.toBe("/ru/catalog");
    expect(isMachinePagePath(machine)).toBe(true);
  });

  it("does not let the catalog index pattern swallow a component route", () => {
    const segments = ["catalog", "components", SEED_A3_AGENT_ID];
    expect(matchesPattern("catalog", segments)).toBe(false);
    expect(matchesPattern("catalog/components/:stableId", segments)).toBe(true);
    expect(
      matchesPattern("catalog/components/:stableId/versions/:version", [
        ...segments,
        "versions",
        "1.0",
      ]),
    ).toBe(true);
  });

  it("derives switch hrefs from the live pathname, not layout x-pathname", () => {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const dock = readFileSync(
      path.resolve(here, "../../src/components/molecules/projection-dock.tsx"),
      "utf8",
    );
    const registry = readFileSync(
      path.resolve(here, "../../src/lib/projection/registry.ts"),
      "utf8",
    );
    expect(dock).toContain("use client");
    expect(dock).toContain("usePathname");
    expect(dock).toContain("projectionSwitchHrefs");
    expect(dock).not.toContain("readCanonicalPathname");
    expect(registry).toContain("componentFactsFromLoaders");
    expect(registry).toContain("readComponentVersion");
  });
});
