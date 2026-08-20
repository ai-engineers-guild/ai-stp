import { describe, expect, it } from "vitest";

import {
  CATALOG_DEFAULT_PAGE_SIZE,
  appliedFilterChips,
  catalogHref,
  catalogQueryToRecord,
  countAppliedFilters,
  parseCatalogSearchParams,
} from "@/lib/catalog-query";
import { defaultCatalogQuery } from "@/lib/catalog-query-defaults";

describe("parseCatalogSearchParams", () => {
  it("defaults to experimental on, page size 25, and a mixed catalog", () => {
    expect(catalogHref("/catalog", {})).toBe("/catalog");
    const result = parseCatalogSearchParams({});
    if (!result.ok) return;
    expect(result.value.resource).toBe("all");
    expect(result.value.includeExperimental).toBe(true);
  });

  it("treats both resource values as the mixed catalog", () => {
    const both = parseCatalogSearchParams({ resource: ["components", "setups"] });
    expect(both.ok).toBe(true);
    if (both.ok) {
      expect(both.value.resource).toBe("all");
    }
    const bothWord = parseCatalogSearchParams({ resource: "both" });
    expect(bothWord.ok).toBe(true);
    if (bothWord.ok) {
      expect(bothWord.value.resource).toBe("all");
    }
    const flagged = parseCatalogSearchParams({ include_experimental: ["1", "true"] });
    expect(flagged.ok).toBe(true);
    if (flagged.ok) {
      expect(flagged.value.includeExperimental).toBe(true);
    }
  });

  it("accepts known keys and tag facets", () => {
    const result = parseCatalogSearchParams({
      q: "python",
      resource: "setups",
      include_experimental: "1",
      tags: ["python", "tests"],
    });
    expect(result.ok).toBe(true);
    if (!result.ok) {
      return;
    }
    expect(result.value.resource).toBe("setups");
    expect(result.value.includeExperimental).toBe(true);
    expect(result.value.tags).toEqual(["python", "tests"]);
  });

  it("opts out of experimental with 0 or false", () => {
    const zero = parseCatalogSearchParams({ include_experimental: "0" });
    expect(zero.ok).toBe(true);
    if (zero.ok) {
      expect(zero.value.includeExperimental).toBe(false);
    }
    const off = parseCatalogSearchParams({ include_experimental: "false" });
    expect(off.ok).toBe(true);
    if (off.ok) {
      expect(off.value.includeExperimental).toBe(false);
    }
  });

  it("rejects unknown filters and invalid tags", () => {
    const unknown = parseCatalogSearchParams({ bogus: "1", q: "x" });
    expect(unknown.ok).toBe(false);
    if (unknown.ok) {
      return;
    }
    expect(unknown.unknownKeys).toEqual(["bogus"]);

    const badTag = parseCatalogSearchParams({ tags: "NOT_VALID" });
    expect(badTag.ok).toBe(false);
    if (badTag.ok) {
      return;
    }
    expect(badTag.invalidTags).toEqual(["NOT_VALID"]);
  });

  it("round-trips preserve record for pagination", () => {
    const parsed = parseCatalogSearchParams({
      resource: "all",
      include_experimental: "1",
      tags: "python,code-review",
      page_size: "5",
    });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) {
      return;
    }
    expect(parsed.value.pageSize).toBe(5);
    const record = catalogQueryToRecord(parsed.value);
    expect(record["include_experimental"]).toBe("1");
    expect(record["tags"]).toBe("python,code-review");
    expect(record["resource"]).toBe("all");
    expect(record["page_size"]).toBe("5");
  });

  it("drops invalid page numbers and calendar dates", () => {
    const page = parseCatalogSearchParams({ page: "0" });
    expect(page.ok).toBe(true);
    if (page.ok) {
      expect(page.value.pageNumber).toBe(1);
    }
    const impossible = parseCatalogSearchParams({ updated_from: "2026-02-31" });
    expect(impossible.ok).toBe(false);
    const malformed = parseCatalogSearchParams({ updated_to: "not-a-date" });
    expect(malformed.ok).toBe(false);
  });

  it("accepts and preserves support filters", () => {
    const parsed = parseCatalogSearchParams({
      support_tier: "beta",
      support_state: "verified",
    });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) {
      return;
    }
    expect(parsed.value.supportTier).toBe("beta");
    expect(parsed.value.supportState).toBe("verified");
    expect(catalogQueryToRecord(parsed.value)).toMatchObject({
      support_tier: "beta",
      support_state: "verified",
    });
  });

  it("treats empty support filter controls as absent", () => {
    const parsed = parseCatalogSearchParams({ support_tier: "", support_state: "" });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) {
      return;
    }
    expect(parsed.value.supportTier).toBeUndefined();
    expect(parsed.value.supportState).toBeUndefined();
  });

  it("rejects unsupported support filter values", () => {
    const parsed = parseCatalogSearchParams({ support_state: "unknown" });
    expect(parsed.ok).toBe(false);
    if (!parsed.ok) {
      expect(parsed.invalidSupport).toEqual(["support_state=unknown"]);
    }
  });

  it("emits explicit include_experimental=0 when opting out", () => {
    const parsed = parseCatalogSearchParams({ include_experimental: "0" });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) {
      return;
    }
    const record = catalogQueryToRecord(parsed.value);
    expect(record["include_experimental"]).toBe("0");
    expect(record["page_size"]).toBe(String(CATALOG_DEFAULT_PAGE_SIZE));
  });

  it("preserves multi-tag order and round-trips reset defaults", () => {
    const parsed = parseCatalogSearchParams({
      tags: ["python", "tests", "security"],
      harness_id: "codex",
    });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) {
      return;
    }
    expect(parsed.value.tags).toEqual(["python", "tests", "security"]);
    expect(countAppliedFilters(parsed.value)).toBe(4);
    const chips = appliedFilterChips(parsed.value);
    expect(chips.map((c) => c.key)).toEqual([
      "tag:python",
      "tag:tests",
      "tag:security",
      "harness_id",
    ]);
    const first = chips[0];
    if (first === undefined) {
      throw new Error("expected first chip");
    }
    const withoutFirstTag = first.without;
    expect(withoutFirstTag.tags).toEqual(["tests", "security"]);
    const reset = defaultCatalogQuery(parsed.value.resource);
    expect(countAppliedFilters(reset)).toBe(0);
    expect(catalogQueryToRecord(reset)).toMatchObject({
      resource: "all",
      include_experimental: "1",
      page_size: String(CATALOG_DEFAULT_PAGE_SIZE),
    });
    expect(catalogQueryToRecord(reset)["tags"]).toBeUndefined();
  });

  it("counts experimental opt-out as one applied filter", () => {
    const parsed = parseCatalogSearchParams({ include_experimental: "0" });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) {
      return;
    }
    expect(countAppliedFilters(parsed.value)).toBe(1);
  });

  it("validates structured query syntax before the API call", () => {
    expect(parseCatalogSearchParams({ q: "NAME:tool AND TAGS IN (python, tests)" }).ok).toBe(true);
    const invalid = parseCatalogSearchParams({ q: "VERIFIED:maybe" });
    expect(invalid.ok).toBe(false);
    if (!invalid.ok) expect(invalid.invalidQuery[0]).toContain("VERIFIED accepts true or false");
  });

  it("serializes, counts, and dismisses every advanced catalog facet", () => {
    const parsed = parseCatalogSearchParams({
      q: "security",
      resource: "components",
      include_experimental: "0",
      harness_id: "codex",
      component_type: "skill",
      harness_ids: "codex,claude-code",
      component_types: "skill,mcp",
      authors: "alice,bob",
      verified_only: "1",
      sort: "likes",
      view: "list",
      support_tier: "primary",
      support_state: "verified",
      page: "3",
    });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;

    expect(countAppliedFilters(parsed.value)).toBe(12);
    expect(catalogQueryToRecord(parsed.value)).toMatchObject({
      q: "security",
      harness_id: "codex",
      component_type: "skill",
      harness_ids: "codex,claude-code",
      component_types: "skill,mcp",
      authors: "alice,bob",
      verified_only: "1",
      sort: "likes",
      view: "list",
      support_tier: "primary",
      support_state: "verified",
      page: "3",
    });

    const chips = appliedFilterChips(parsed.value);
    expect(chips.map(({ key }) => key)).toEqual([
      "harness_id",
      "component_type",
      "harness:codex",
      "harness:claude-code",
      "type:skill",
      "type:mcp",
      "author:alice",
      "author:bob",
      "verified_only",
      "support_tier",
      "support_state",
      "include_experimental",
    ]);
    for (const chip of chips) {
      expect(chip.without.cursor).toBeUndefined();
    }
    expect(chips.find(({ key }) => key === "verified_only")?.without.verifiedOnly).toBe(false);
    expect(chips.find(({ key }) => key === "support_tier")?.without.supportTier).toBeUndefined();
    expect(chips.find(({ key }) => key === "support_state")?.without.supportState).toBeUndefined();
    expect(
      chips.find(({ key }) => key === "include_experimental")?.without.includeExperimental,
    ).toBe(true);
  });

  it("rejects invalid structured-query boundaries and list operands", () => {
    for (const q of ["NAME:(", "NAME:tool AND", "UNKNOWN:value", "OR NAME:tool", "NAME:tool OR"]) {
      const result = parseCatalogSearchParams({ q });
      expect(result.ok, q).toBe(false);
    }
  });

  it("validates quoted values, nesting limits, length, and balanced parentheses", () => {
    expect(parseCatalogSearchParams({ q: `NAME:"a \\"quoted\\" tool"` }).ok).toBe(true);
    for (const q of [
      `NAME:"unterminated`,
      "NAME:value)",
      "(((((((((NAME:value)))))))))",
      "x".repeat(501),
    ]) {
      expect(parseCatalogSearchParams({ q }).ok, q).toBe(false);
    }
  });

  it("normalizes repeated facet values and bounds invalid pagination inputs", () => {
    const parsed = parseCatalogSearchParams({
      tags: ["python", "python", " tests "],
      harness_ids: ["codex, claude-code", "codex", ""],
      authors: ["alice", "alice,bob"],
      cursor: "opaque-token",
      page_size: "999",
      page: "99999",
      sort: "updated_at",
    });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.value.tags).toEqual(["python", "tests"]);
    expect(parsed.value.harnessIds).toEqual(["codex", "claude-code"]);
    expect(parsed.value.authors).toEqual(["alice", "bob"]);
    expect(parsed.value.cursor).toBe("opaque-token");
    expect(parsed.value.pageSize).toBe(100);
    expect(parsed.value.pageNumber).toBe(10_000);
    expect(parsed.value.sort).toBe("updated_at");

    const fallback = parseCatalogSearchParams({ page_size: "none", page: "-2", sort: "unknown" });
    expect(fallback.ok).toBe(true);
    if (fallback.ok) {
      expect(fallback.value.pageSize).toBe(CATALOG_DEFAULT_PAGE_SIZE);
      expect(fallback.value.pageNumber).toBe(1);
      expect(fallback.value.sort).toBe("relevance");
    }
  });

  it("reports all independent URL validation categories together", () => {
    const parsed = parseCatalogSearchParams({
      unknown: "1",
      tags: "INVALID_TAG",
      support_tier: "unsupported",
      q: "VERIFIED:maybe",
    });
    expect(parsed.ok).toBe(false);
    if (!parsed.ok) {
      expect(parsed.unknownKeys).toEqual(["unknown"]);
      expect(parsed.invalidTags).toEqual(["INVALID_TAG"]);
      expect(parsed.invalidSupport).toEqual(["support_tier=unsupported"]);
      expect(parsed.invalidQuery).toHaveLength(1);
    }
  });

  it("folds legacy singleton country_code and service_domain into multi filters", () => {
    const parsed = parseCatalogSearchParams({
      country_code: "kz",
      service_domain: "Kaspi.KZ",
    });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.value.countryCodes).toEqual(["KZ"]);
    expect(parsed.value.serviceDomains).toEqual(["kaspi.kz"]);
    expect(parsed.value.countryCode).toBeUndefined();
    expect(parsed.value.serviceDomain).toBeUndefined();
    expect(countAppliedFilters(parsed.value)).toBe(2);
    expect(catalogQueryToRecord(parsed.value)).toMatchObject({
      country_codes: "KZ",
      service_domains: "kaspi.kz",
    });
    expect(catalogQueryToRecord(parsed.value)["country_code"]).toBeUndefined();
    expect(appliedFilterChips(parsed.value).map(({ key }) => key)).toEqual([
      "service:kaspi.kz",
      "country:KZ",
    ]);
    const legacy = { ...parsed.value, countryCode: "KZ", serviceDomain: "kaspi.kz" };
    expect(catalogQueryToRecord(legacy)).toMatchObject({
      country_code: "KZ",
      service_domain: "kaspi.kz",
    });
  });

  it("treats a singleton unspecified country as the multi sentinel", () => {
    const parsed = parseCatalogSearchParams({ country_code: "UNSPECIFIED" });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.value.countryCodes).toEqual(["unspecified"]);
    expect(countAppliedFilters(parsed.value)).toBe(1);
  });

  it("serializes multi and unspecified country and service filters as chips", () => {
    const parsed = parseCatalogSearchParams({
      country_codes: ["kz", "unspecified"],
      service_domains: ["Kaspi.KZ", "unspecified"],
    });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.value.countryCodes).toEqual(["KZ", "unspecified"]);
    expect(parsed.value.serviceDomains).toEqual(["kaspi.kz", "unspecified"]);
    expect(countAppliedFilters(parsed.value)).toBe(4);
    expect(catalogQueryToRecord(parsed.value)).toMatchObject({
      country_codes: "KZ,unspecified",
      service_domains: "kaspi.kz,unspecified",
    });
    const chips = appliedFilterChips(parsed.value);
    expect(chips.map(({ key }) => key)).toEqual([
      "service:kaspi.kz",
      "service:unspecified",
      "country:KZ",
      "country:unspecified",
    ]);
    expect(chips[0]?.without.serviceDomains).toEqual(["unspecified"]);
  });

  it("accepts both as an alias for mixed resource and old singleton resource URLs", () => {
    const both = parseCatalogSearchParams({ resource: "both" });
    expect(both.ok).toBe(true);
    if (both.ok) expect(both.value.resource).toBe("all");
    const all = parseCatalogSearchParams({ resource: "all" });
    expect(all.ok).toBe(true);
    if (all.ok) expect(all.value.resource).toBe("all");
    const components = parseCatalogSearchParams({ resource: "components" });
    expect(components.ok).toBe(true);
    if (components.ok) expect(components.value.resource).toBe("components");
  });

  it("parses inclusive updated date bounds and rejects reversed or invalid dates", () => {
    const parsed = parseCatalogSearchParams({
      updated_from: "2026-01-01",
      updated_to: "2026-01-31",
    });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.value.updatedFrom).toBe("2026-01-01");
    expect(parsed.value.updatedTo).toBe("2026-01-31");
    expect(countAppliedFilters(parsed.value)).toBe(2);
    expect(catalogQueryToRecord(parsed.value)).toMatchObject({
      updated_from: "2026-01-01",
      updated_to: "2026-01-31",
    });

    const fromOnly = parseCatalogSearchParams({ updated_from: "2026-02-01" });
    expect(fromOnly.ok).toBe(true);
    if (fromOnly.ok) expect(fromOnly.value.updatedTo).toBeUndefined();

    const reversed = parseCatalogSearchParams({
      updated_from: "2026-02-02",
      updated_to: "2026-02-01",
    });
    expect(reversed.ok).toBe(false);
    if (!reversed.ok) expect(reversed.invalidQuery).toContain("updated_from>updated_to");

    const invalid = parseCatalogSearchParams({ updated_from: "2026-13-40" });
    expect(invalid.ok).toBe(false);
    if (!invalid.ok) expect(invalid.invalidQuery[0]).toContain("updated_from=");
  });

  it("round-trips cards view and sort direction explicitly", () => {
    const parsed = parseCatalogSearchParams({ view: "cards", sort_direction: "asc" });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.value.view).toBe("cards");
    expect(parsed.value.sortDirection).toBe("asc");
    expect(catalogQueryToRecord(parsed.value)).toMatchObject({
      view: "cards",
      sort_direction: "asc",
    });
  });

  it("keeps independent Both-mode pages and drops a shared cursor", () => {
    const parsed = parseCatalogSearchParams({
      resource: "all",
      cursor: "shared-cursor",
      setups_page: "2",
      components_page: "3",
    });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.value.resource).toBe("all");
    expect(parsed.value.cursor).toBe("shared-cursor");
    expect(parsed.value.setupsPage).toBe(2);
    expect(parsed.value.componentsPage).toBe(3);
    expect(catalogQueryToRecord(parsed.value)).toMatchObject({
      resource: "all",
      setups_page: "2",
      components_page: "3",
    });
    expect(catalogQueryToRecord(parsed.value).cursor).toBeUndefined();
  });

  it("serializes a single updated bound without inventing the other edge", () => {
    const parsed = parseCatalogSearchParams({ updated_to: "2026-03-01" });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.value.updatedFrom).toBeUndefined();
    expect(parsed.value.updatedTo).toBe("2026-03-01");
    const record = catalogQueryToRecord(parsed.value);
    expect(record["updated_to"]).toBe("2026-03-01");
    expect(record["updated_from"]).toBeUndefined();
    expect(appliedFilterChips(parsed.value).map((chip) => chip.key)).toEqual(["updated_to"]);
  });
});
