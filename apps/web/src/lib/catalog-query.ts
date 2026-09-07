/* eslint-disable max-lines -- This is the single canonical parser/serializer boundary. */

/**
 * Catalog search query parsing for the web (SPEC-022 REQ-2206, http-api.md).
 * Unknown query keys are a typed validation error, never silently ignored.
 */

import { asCursorToken, type CursorToken } from "@/lib/brands";
import { normalizeCountryFilter, normalizeDomainFilter } from "@/lib/catalog-relation-filters";
import { isHarnessFacet, isValidTagId, MAX_TAGS } from "@/lib/tag-vocabulary";

export const CATALOG_DEFAULT_PAGE_SIZE = 25;

export { CATALOG_UNSPECIFIED_FILTER } from "@/lib/catalog-relation-filters";

/** Keys the web catalog form may emit (includes web-only `resource`). */
export const CATALOG_WEB_QUERY_KEYS = frozenset([
  "q",
  "cursor",
  "resource",
  "include_experimental",
  "tags",
  "harness_id",
  "component_type",
  "harness_ids",
  "component_types",
  "authors",
  "verification",
  "verified_only",
  "min_safety_percent",
  "sort",
  "sort_direction",
  "view",
  "support_tier",
  "support_state",
  "service_domain",
  "country_code",
  "service_domains",
  "country_codes",
  "updated_from",
  "updated_to",
  "verification",
  "min_safety_percent",
  "page_size",
  "page",
  "setups_page",
  "components_page",
  "family_id",
  "family_alignment",
  "member_harness_id",
]);

/** Keys forwarded to the platform API search endpoints. */
export const CATALOG_API_QUERY_KEYS = frozenset([
  "q",
  "cursor",
  "include_experimental",
  "tags",
  "harness_id",
  "component_type",
  "support_tier",
  "support_state",
  "service_domain",
  "country_code",
  "service_domains",
  "country_codes",
  "updated_from",
  "updated_to",
  "page_size",
  "schema_version",
  "family_id",
  "family_alignment",
  "member_harness_id",
]);

function frozenset(values: string[]): ReadonlySet<string> {
  return new Set(values);
}

export type CatalogResource = "components" | "setups" | "all";

export type ParsedCatalogQuery = {
  q: string;
  resource: CatalogResource;
  /** Default true: browse shows experimental seed without an extra click. */
  includeExperimental: boolean;
  cursor: CursorToken | undefined;
  tags: string[];
  harnessId: string | undefined;
  componentType: string | undefined;
  harnessIds: string[];
  componentTypes: string[];
  authors: string[];
  verification: Array<"verified" | "not_verified">;
  verifiedOnly: boolean;
  minSafetyPercent: 75 | 85 | 90 | 99 | undefined;
  sort: "relevance" | "updated_at" | "likes";
  sortDirection: "asc" | "desc";
  view: "cards" | "list";
  supportTier: "primary" | "beta" | undefined;
  supportState: "verified" | "stale" | "missing" | "not_verified" | undefined;
  serviceDomain?: string;
  countryCode?: string;
  serviceDomains?: string[];
  countryCodes?: string[];
  updatedFrom?: string;
  updatedTo?: string;
  familyId?: string;
  familyAlignment?: "aligned" | "diverged" | "unknown" | "missing";
  memberHarnessId?: string;
  /** Always resolved; default {@link CATALOG_DEFAULT_PAGE_SIZE}. */
  pageSize: number;
  pageNumber: number;
  setupsPage?: number;
  componentsPage?: number;
};

export type CatalogQueryParseResult =
  | { ok: true; value: ParsedCatalogQuery }
  | {
      ok: false;
      unknownKeys: string[];
      invalidTags: string[];
      invalidSupport: string[];
      invalidQuery: string[];
    };

/**
 * Parse Next.js searchParams for the catalog page.
 * `tags` may appear once (comma-separated) or as repeated keys.
 * Defaults: resource=all, include_experimental=true, page_size=25.
 */
// Parsing is kept in one boundary so malformed URL state cannot reach the API client.
// eslint-disable-next-line max-lines-per-function, complexity
export function parseCatalogSearchParams(
  raw: Record<string, string | string[] | undefined>,
): CatalogQueryParseResult {
  const keys = Object.keys(raw).filter((key) => raw[key] !== undefined);
  const unknownKeys = keys.filter((key) => !CATALOG_WEB_QUERY_KEYS.has(key)).sort();
  const tags = normalizeTags(raw["tags"]);
  const invalidTags = tags.filter((tag) => !isValidTagId(tag));
  const supportTierRaw = firstString(raw["support_tier"]) || undefined;
  const supportStateRaw = firstString(raw["support_state"]) || undefined;
  const verification = normalizeValues(raw["verification"]);
  const verificationValues = new Set(["verified", "not_verified"]);
  const minSafetyRaw = firstString(raw["min_safety_percent"])?.trim() || undefined;
  const minSafetyValue = minSafetyRaw ? Number.parseInt(minSafetyRaw, 10) : undefined;
  const validSafetyValues = [75, 85, 90, 99] as const;
  const minSafetyPercent = validSafetyValues.includes(
    minSafetyValue as (typeof validSafetyValues)[number],
  )
    ? (minSafetyValue as (typeof validSafetyValues)[number])
    : undefined;
  const serviceDomain = firstString(raw["service_domain"])?.trim()
    ? normalizeDomainFilter(firstString(raw["service_domain"]) ?? "")
    : undefined;
  const countryCode = firstString(raw["country_code"])?.trim()
    ? normalizeCountryFilter(firstString(raw["country_code"]) ?? "")
    : undefined;
  const serviceDomains = withSingleton(
    normalizeValues(raw["service_domains"]).map(normalizeDomainFilter),
    serviceDomain,
  );
  const countryCodes = withSingleton(
    normalizeValues(raw["country_codes"]).map(normalizeCountryFilter),
    countryCode,
  );
  const updatedFromRaw = firstString(raw["updated_from"])?.trim() || undefined;
  const updatedToRaw = firstString(raw["updated_to"])?.trim() || undefined;
  const updatedFrom = updatedFromRaw ? parseIsoDate(updatedFromRaw) : undefined;
  const updatedTo = updatedToRaw ? parseIsoDate(updatedToRaw) : undefined;
  const familyIdRaw = firstString(raw["family_id"])?.trim() || undefined;
  const familyAlignmentRaw = firstString(raw["family_alignment"])?.trim() || undefined;
  const memberHarnessRaw = firstString(raw["member_harness_id"])?.trim() || undefined;
  const invalidSupport = [
    ...(supportTierRaw !== undefined && !["primary", "beta"].includes(supportTierRaw)
      ? [`support_tier=${supportTierRaw}`]
      : []),
    ...(supportStateRaw !== undefined &&
    !["verified", "stale", "missing", "not_verified"].includes(supportStateRaw)
      ? [`support_state=${supportStateRaw}`]
      : []),
    ...(familyAlignmentRaw !== undefined &&
    !["aligned", "diverged", "unknown", "missing"].includes(familyAlignmentRaw)
      ? [`family_alignment=${familyAlignmentRaw}`]
      : []),
    ...(memberHarnessRaw !== undefined && !isHarnessFacet(memberHarnessRaw)
      ? [`member_harness_id=${memberHarnessRaw}`]
      : []),
    ...verification
      .filter((value) => !verificationValues.has(value))
      .map((value) => `verification=${value}`),
    ...(verification.length > 2 ? ["verification: maximum 2 values"] : []),
    ...(minSafetyRaw !== undefined && minSafetyPercent === undefined
      ? [`min_safety_percent=${minSafetyRaw}`]
      : []),
  ];
  const qRaw = firstString(raw["q"]) ?? "";
  const queryError = validateCatalogQuery(qRaw);
  const invalidQuery = queryError ? [queryError] : [];
  if (tags.length > MAX_TAGS) invalidQuery.push(`tags: maximum ${MAX_TAGS}`);
  if (updatedFromRaw && !updatedFrom) invalidQuery.push(`updated_from=${updatedFromRaw}`);
  if (updatedToRaw && !updatedTo) invalidQuery.push(`updated_to=${updatedToRaw}`);
  if (updatedFrom && updatedTo && updatedFrom > updatedTo) {
    invalidQuery.push("updated_from>updated_to");
  }

  if (
    unknownKeys.length > 0 ||
    invalidTags.length > 0 ||
    invalidSupport.length > 0 ||
    invalidQuery.length > 0
  ) {
    return { ok: false, unknownKeys, invalidTags, invalidSupport, invalidQuery };
  }

  const resourceValues = normalizeValues(raw["resource"]);
  let resource: CatalogResource =
    resourceValues.includes("components") && resourceValues.includes("setups")
      ? "all"
      : resourceValues[0] === "setups"
        ? "setups"
        : resourceValues[0] === "components"
          ? "components"
          : resourceValues[0] === "both" || resourceValues[0] === "all"
            ? "all"
            : "all";

  const experimentalRaw = firstString(raw["include_experimental"]);
  // Default ON: first-party seed is experimental (SPEC-021); opt out with 0/false.
  const includeExperimental =
    experimentalRaw === undefined || experimentalRaw === ""
      ? true
      : experimentalRaw === "1" || experimentalRaw === "true";

  const cursorRaw = firstString(raw["cursor"]);
  const harnessId = firstString(raw["harness_id"]) || undefined;
  const componentType = firstString(raw["component_type"]) || undefined;
  const harnessIds = normalizeValues(raw["harness_ids"]);
  const componentTypes = normalizeValues(raw["component_types"]);
  const authors = normalizeValues(raw["authors"]);
  const verifiedOnly =
    verification.length === 0 && ["1", "true"].includes(firstString(raw["verified_only"]) ?? "");
  if (
    resource !== "components" &&
    (componentType || componentTypes.length > 0 || minSafetyPercent !== undefined)
  ) {
    resource = "components";
  }
  const sortRaw = firstString(raw["sort"]);
  const sort = ["updated_at", "likes"].includes(sortRaw ?? "")
    ? (sortRaw as "updated_at" | "likes")
    : "relevance";
  const sortDirection = firstString(raw["sort_direction"]) === "asc" ? "asc" : "desc";
  const view = firstString(raw["view"]) === "cards" ? "cards" : "list";
  const pageSizeRaw = firstString(raw["page_size"]);
  const pageSizeParsed = pageSizeRaw ? Number.parseInt(pageSizeRaw, 10) : Number.NaN;
  const pageSize =
    Number.isFinite(pageSizeParsed) && pageSizeParsed > 0
      ? Math.min(pageSizeParsed, 100)
      : CATALOG_DEFAULT_PAGE_SIZE;
  const pageRaw = Number.parseInt(firstString(raw["page"]) ?? "1", 10);
  const pageNumber = Number.isFinite(pageRaw) && pageRaw > 0 ? Math.min(pageRaw, 10_000) : 1;
  const setupsPage = parseOptionalPage(firstString(raw["setups_page"]));
  const componentsPage = parseOptionalPage(firstString(raw["components_page"]));

  return {
    ok: true,
    value: {
      q: qRaw,
      resource,
      includeExperimental,
      cursor: cursorRaw ? asCursorToken(cursorRaw) : undefined,
      tags,
      harnessId,
      componentType,
      harnessIds,
      componentTypes,
      authors,
      verification: verification.filter((value): value is "verified" | "not_verified" =>
        verificationValues.has(value),
      ),
      verifiedOnly,
      minSafetyPercent,
      sort,
      sortDirection,
      view,
      supportTier: supportTierRaw as "primary" | "beta" | undefined,
      supportState: supportStateRaw as
        "verified" | "stale" | "missing" | "not_verified" | undefined,
      serviceDomains,
      countryCodes,
      ...(updatedFrom ? { updatedFrom } : {}),
      ...(updatedTo ? { updatedTo } : {}),
      ...(familyIdRaw ? { familyId: familyIdRaw } : {}),
      ...(familyAlignmentRaw &&
      ["aligned", "diverged", "unknown", "missing"].includes(familyAlignmentRaw)
        ? {
            familyAlignment: familyAlignmentRaw as "aligned" | "diverged" | "unknown" | "missing",
          }
        : {}),
      ...(memberHarnessRaw && isHarnessFacet(memberHarnessRaw)
        ? { memberHarnessId: memberHarnessRaw }
        : {}),
      pageSize,
      pageNumber,
      ...(setupsPage ? { setupsPage } : {}),
      ...(componentsPage ? { componentsPage } : {}),
    },
  };
}

/** Fast UX validation. The backend parser remains the authoritative boundary. */
export function validateCatalogQuery(source: string): string | null {
  if (source.length > 500) return "offset 500: query is too long";
  let quote: string | null = null;
  let depth = 0;
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index] ?? "";
    if (quote) {
      if (char === "\\") index += 1;
      else if (char === quote) quote = null;
      continue;
    }
    if (char === '"' || char === "'") quote = char;
    else if (char === "(") {
      depth += 1;
      if (depth > 8) return `offset ${index}: query nesting is too deep`;
    } else if (char === ")") {
      depth -= 1;
      if (depth < 0) return `offset ${index}: unexpected closing parenthesis`;
    }
  }
  if (quote) return `offset ${source.lastIndexOf(quote)}: unterminated quoted value`;
  if (depth > 0) return `offset ${source.lastIndexOf("(")}: missing closing parenthesis`;
  const syntax = maskQuotedCatalogQuery(source);
  const fieldUse = /\b([A-Z][A-Z_]*)\s*(?::|(?:NOT\s+)?IN\s*\()/gi;
  for (const match of syntax.matchAll(fieldUse)) {
    if (!/^(?:NAME|TAGS|HARNESS|TYPE|AUTHOR|VERIFIED)$/i.test(match[1] ?? "")) {
      return `offset ${match.index}: unknown search field`;
    }
  }
  for (const match of syntax.matchAll(/\bVERIFIED\s*:\s*([^\s)]+)/gi)) {
    if (!/^(?:true|false)$/i.test(match[1] ?? "")) {
      return `offset ${match.index}: VERIFIED accepts true or false`;
    }
  }
  if (/\b(?:AND|OR)\s*$/i.test(syntax) || /^\s*(?:AND|OR|IN)\b/i.test(syntax)) {
    return `offset ${Math.max(0, syntax.search(/(?:AND|OR|IN)\s*$/i))}: operator is missing an operand`;
  }
  return null;
}

function maskQuotedCatalogQuery(source: string): string {
  let quote: string | null = null;
  let masked = "";
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index] ?? "";
    if (quote) {
      if (char === quote && source[index - 1] !== "\\") quote = null;
      masked += " ";
    } else if (char === '"' || char === "'") {
      quote = char;
      masked += "x";
    } else {
      masked += char;
    }
  }
  return masked;
}

function parseOptionalPage(value: string | undefined): number | undefined {
  if (!value) return undefined;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) return undefined;
  return Math.min(parsed, 10_000);
}

function parseIsoDate(value: string): string | undefined {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  const instant = new Date(Date.UTC(year, month - 1, day));
  if (
    instant.getUTCFullYear() !== year ||
    instant.getUTCMonth() !== month - 1 ||
    instant.getUTCDate() !== day
  ) {
    return undefined;
  }
  return value;
}

function firstString(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

function normalizeTags(value: string | string[] | undefined): string[] {
  if (value === undefined) {
    return [];
  }
  const parts = Array.isArray(value) ? value : value.split(",");
  const seen = new Set<string>();
  const result: string[] = [];
  for (const part of parts) {
    const tag = part.trim();
    if (tag.length === 0 || seen.has(tag)) {
      continue;
    }
    seen.add(tag);
    result.push(tag);
  }
  return result;
}

function normalizeValues(value: string | string[] | undefined): string[] {
  if (value === undefined) return [];
  const values = (Array.isArray(value) ? value : [value]).flatMap((item) => item.split(","));
  return [...new Set(values.map((item) => item.trim()).filter(Boolean))];
}

function withSingleton(values: string[], singleton: string | undefined): string[] {
  if (!singleton || values.includes(singleton)) return values;
  return [singleton, ...values];
}

/** Build query record for pagination / form preserve (string values only). */
// eslint-disable-next-line complexity
export function catalogQueryToRecord(
  query: ParsedCatalogQuery,
  extra: Record<string, string> = {},
): Record<string, string> {
  const record: Record<string, string> = {
    resource: query.resource,
    page_size: String(query.pageSize),
    page: String(query.pageNumber),
    ...extra,
  };
  if (query.q) {
    record["q"] = query.q;
  }
  // Always emit so "next page" and form re-submit keep the default-on semantics.
  if (query.includeExperimental) {
    record["include_experimental"] = "1";
  } else {
    record["include_experimental"] = "0";
  }
  if (query.tags.length > 0) {
    record["tags"] = query.tags.join(",");
  }
  if (query.harnessId) {
    record["harness_id"] = query.harnessId;
  }
  if (query.componentType) {
    record["component_type"] = query.componentType;
  }
  if (query.harnessIds.length > 0) record["harness_ids"] = query.harnessIds.join(",");
  if (query.componentTypes.length > 0) record["component_types"] = query.componentTypes.join(",");
  if (query.authors.length > 0) record["authors"] = query.authors.join(",");
  if (query.verification.length > 0) record["verification"] = query.verification.join(",");
  if (query.verifiedOnly) record["verified_only"] = "1";
  if (query.minSafetyPercent !== undefined) {
    record["min_safety_percent"] = String(query.minSafetyPercent);
  }
  if (query.sort !== "relevance") record["sort"] = query.sort;
  if (query.sortDirection !== "desc") record["sort_direction"] = query.sortDirection;
  record["view"] = query.view;
  if (query.supportTier) {
    record["support_tier"] = query.supportTier;
  }
  if (query.supportState) {
    record["support_state"] = query.supportState;
  }
  if (query.serviceDomain) record["service_domain"] = query.serviceDomain;
  if (query.countryCode) record["country_code"] = query.countryCode;
  if (query.serviceDomains?.length) record["service_domains"] = query.serviceDomains.join(",");
  if (query.countryCodes?.length) record["country_codes"] = query.countryCodes.join(",");
  writeOptional(record, "updated_from", query.updatedFrom);
  writeOptional(record, "updated_to", query.updatedTo);
  writeOptional(record, "family_id", query.familyId);
  writeOptional(record, "family_alignment", query.familyAlignment);
  writeOptional(record, "member_harness_id", query.memberHarnessId);
  if (query.resource === "all") {
    writeOptional(record, "setups_page", query.setupsPage ? String(query.setupsPage) : undefined);
    writeOptional(
      record,
      "components_page",
      query.componentsPage ? String(query.componentsPage) : undefined,
    );
  }
  return record;
}

function writeOptional(record: Record<string, string>, key: string, value: string | undefined) {
  if (value) record[key] = value;
}

export function catalogHref(
  basePath: string,
  query: Record<string, string | undefined | null>,
): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value) params.set(key, value);
  }
  const encoded = params.toString();
  return encoded ? `${basePath}?${encoded}` : basePath;
}

export {
  appliedFilterChips,
  countAppliedFilters,
  type AppliedFilterChip,
} from "@/lib/catalog-query-chips";
