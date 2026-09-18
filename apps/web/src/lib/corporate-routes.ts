const CORPORATE_QUERY_KEYS = new Set([
  "query",
  "q",
  "view",
  "sort",
  "is_lead",
  "page",
  "page_size",
  "lead_ids",
  "team_ids",
  "project_ids",
  "technology_ids",
  "technology_category_ids",
  "category_ids",
  "job_title_ids",
  "owner_ids",
  "maintainer_ids",
  "assignment",
  "corporate_verified",
  "include_experimental",
]);

/** Preserve only known, URL-safe corporate filters during permanent redirects. */
export function safeCorporateQuery(
  raw: Record<string, string | string[] | undefined>,
  extra: Record<string, string> = {},
): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(raw)) {
    if (!CORPORATE_QUERY_KEYS.has(key)) continue;
    for (const item of Array.isArray(value) ? value : value ? [value] : []) {
      if (item.length <= 256) query.append(key, item);
    }
  }
  for (const [key, value] of Object.entries(extra)) query.set(key, value);
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

export function corporateEmployeePath(id?: string): string {
  return id ? `/corporate/employees/${encodeURIComponent(id)}` : "/corporate/employees";
}

export function corporateCatalogPath(): string {
  return "/corporate/catalog";
}
