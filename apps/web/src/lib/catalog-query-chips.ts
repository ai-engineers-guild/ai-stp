import type { ParsedCatalogQuery } from "@/lib/catalog-query";

/**
 * Count filters that deviate from contract defaults (SPEC-037 REQ-3701).
 * Does not count search text or resource selector (always visible).
 * Default include_experimental=true is not an "applied" filter.
 */
export function countAppliedFilters(query: ParsedCatalogQuery): number {
  let n = 0;
  n += query.tags.length;
  if (query.harnessId) n += 1;
  if (query.componentType) n += 1;
  n += query.harnessIds.length + query.componentTypes.length + query.authors.length;
  if (query.verifiedOnly) n += 1;
  if (query.supportTier) n += 1;
  if (query.supportState) n += 1;
  if (query.serviceDomain && !(query.serviceDomains ?? []).includes(query.serviceDomain)) n += 1;
  if (query.countryCode && !(query.countryCodes ?? []).includes(query.countryCode)) n += 1;
  n += (query.serviceDomains?.length ?? 0) + (query.countryCodes?.length ?? 0);
  if (query.updatedFrom) n += 1;
  if (query.updatedTo) n += 1;
  if (!query.includeExperimental) n += 1;
  return n;
}

export type AppliedFilterChip = {
  key: string;
  label: string;
  /** Query after removing this chip (for href). */
  without: ParsedCatalogQuery;
};

function resetCatalogPage(query: ParsedCatalogQuery): ParsedCatalogQuery {
  const next = { ...query, cursor: undefined, pageNumber: 1 };
  delete next.setupsPage;
  delete next.componentsPage;
  return next;
}

/** Build dismissible chip models for applied extra filters (REQ-3702). */
export function appliedFilterChips(query: ParsedCatalogQuery): AppliedFilterChip[] {
  const chips: AppliedFilterChip[] = [];
  if (query.updatedFrom) {
    const { updatedFrom, ...rest } = query;
    chips.push({
      key: "updated_from",
      label: updatedFrom,
      without: resetCatalogPage(rest),
    });
  }
  if (query.updatedTo) {
    const { updatedTo, ...rest } = query;
    chips.push({
      key: "updated_to",
      label: updatedTo,
      without: resetCatalogPage(rest),
    });
  }
  const serviceDomains = query.serviceDomains ?? [];
  const countryCodes = query.countryCodes ?? [];
  if (query.serviceDomain && !serviceDomains.includes(query.serviceDomain)) {
    const { serviceDomain, ...rest } = query;
    chips.push({
      key: `service:${serviceDomain}`,
      label: serviceDomain,
      without: resetCatalogPage(rest),
    });
  }
  if (query.countryCode && !countryCodes.includes(query.countryCode)) {
    const { countryCode, ...rest } = query;
    chips.push({
      key: `country:${countryCode}`,
      label: countryCode,
      without: resetCatalogPage(rest),
    });
  }
  for (const domain of serviceDomains) {
    chips.push({
      key: `service:${domain}`,
      label: domain,
      without: {
        ...query,
        serviceDomains: serviceDomains.filter((value) => value !== domain),
        cursor: undefined,
        pageNumber: 1,
      },
    });
  }
  for (const code of countryCodes) {
    chips.push({
      key: `country:${code}`,
      label: code,
      without: {
        ...query,
        countryCodes: countryCodes.filter((value) => value !== code),
        cursor: undefined,
        pageNumber: 1,
      },
    });
  }
  for (const tag of query.tags) {
    chips.push({
      key: `tag:${tag}`,
      label: tag,
      without: { ...query, tags: query.tags.filter((item) => item !== tag), cursor: undefined },
    });
  }
  if (query.harnessId) {
    chips.push({
      key: "harness_id",
      label: query.harnessId,
      without: { ...query, harnessId: undefined, cursor: undefined },
    });
  }
  if (query.componentType) {
    chips.push({
      key: "component_type",
      label: query.componentType,
      without: { ...query, componentType: undefined, cursor: undefined },
    });
  }
  for (const harness of query.harnessIds) {
    chips.push({
      key: `harness:${harness}`,
      label: harness,
      without: {
        ...query,
        harnessIds: query.harnessIds.filter((value) => value !== harness),
        cursor: undefined,
        pageNumber: 1,
      },
    });
  }
  for (const type of query.componentTypes) {
    chips.push({
      key: `type:${type}`,
      label: type,
      without: {
        ...query,
        componentTypes: query.componentTypes.filter((value) => value !== type),
        cursor: undefined,
        pageNumber: 1,
      },
    });
  }
  for (const author of query.authors) {
    chips.push({
      key: `author:${author}`,
      label: author,
      without: {
        ...query,
        authors: query.authors.filter((value) => value !== author),
        cursor: undefined,
        pageNumber: 1,
      },
    });
  }
  if (query.verifiedOnly) {
    chips.push({
      key: "verified_only",
      label: "verified",
      without: { ...query, verifiedOnly: false, cursor: undefined, pageNumber: 1 },
    });
  }
  if (query.supportTier) {
    chips.push({
      key: "support_tier",
      label: query.supportTier,
      without: { ...query, supportTier: undefined, cursor: undefined },
    });
  }
  if (query.supportState) {
    chips.push({
      key: "support_state",
      label: query.supportState,
      without: { ...query, supportState: undefined, cursor: undefined },
    });
  }
  if (!query.includeExperimental) {
    chips.push({
      key: "include_experimental",
      label: "experimental:off",
      without: { ...query, includeExperimental: true, cursor: undefined },
    });
  }
  return chips.map((chip) => ({ ...chip, without: resetCatalogPage(chip.without) }));
}
