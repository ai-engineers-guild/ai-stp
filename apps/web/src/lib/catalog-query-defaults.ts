import {
  CATALOG_DEFAULT_PAGE_SIZE,
  type CatalogResource,
  type ParsedCatalogQuery,
} from "@/lib/catalog-query";

/** Contract defaults for Reset all (REQ-3702). */
export function defaultCatalogQuery(resource: CatalogResource = "all"): ParsedCatalogQuery {
  return {
    q: "",
    resource,
    includeExperimental: true,
    cursor: undefined,
    tags: [],
    harnessId: undefined,
    componentType: undefined,
    harnessIds: [],
    componentTypes: [],
    authors: [],
    verifiedOnly: false,
    sort: "relevance",
    sortDirection: "desc",
    view: "list",
    supportTier: undefined,
    supportState: undefined,
    serviceDomains: [],
    countryCodes: [],
    pageSize: CATALOG_DEFAULT_PAGE_SIZE,
    pageNumber: 1,
  };
}
