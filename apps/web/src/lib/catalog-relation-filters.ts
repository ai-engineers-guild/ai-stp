/** Sentinel for country/service filters that match objects with no assignment. */
export const CATALOG_UNSPECIFIED_FILTER = "unspecified";

export function normalizeCountryFilter(value: string): string {
  return value.toLowerCase() === CATALOG_UNSPECIFIED_FILTER
    ? CATALOG_UNSPECIFIED_FILTER
    : value.toUpperCase();
}

export function normalizeDomainFilter(value: string): string {
  return value.toLowerCase();
}
