import { listExternalProducts, searchComponents, searchSetups } from "@/lib/api/catalog";
import type { ComponentListResponse, SetupListResponse } from "@/lib/api/generated/types.gen";
import { readPublisherProfile } from "@/lib/api/public-profile";
import { asAccountId, type AccountId } from "@/lib/brands";
import type { ParsedCatalogQuery } from "@/lib/catalog-query";

export const PUBLISHER_PROFILE_CONCURRENCY = 6;

export type PublisherAuthorProfile = {
  displayName: string | null;
  avatarUrl: string | null;
};

export type CatalogReadDeps = {
  listExternalProducts: typeof listExternalProducts;
  searchComponents: typeof searchComponents;
  searchSetups: typeof searchSetups;
};

const defaultCatalogReadDeps: CatalogReadDeps = {
  listExternalProducts,
  searchComponents,
  searchSetups,
};

type CatalogSearchInput = Parameters<typeof searchComponents>[0];

// Field-by-field copy of the parsed catalog query; keep one function so callers
// cannot drop a filter when adding an axis.
// eslint-disable-next-line complexity
export function catalogSearchInput(
  query: ParsedCatalogQuery,
  resource: "components" | "setups",
): CatalogSearchInput {
  const setupsPageNumber = query.setupsPage ?? query.pageNumber;
  const componentsPageNumber = query.componentsPage ?? query.pageNumber;
  const input: CatalogSearchInput = {
    verified_only: query.verifiedOnly,
    sort: query.sort,
    sort_direction: query.sortDirection,
    page_size: query.pageSize,
    include_experimental: query.includeExperimental,
  };
  if (query.q) input.q = query.q;
  if (query.resource !== "all" && query.cursor) input.cursor = query.cursor;
  if (query.tags.length > 0) input.tags = query.tags;
  if (query.harnessId) input.harness_id = query.harnessId;
  if (resource === "components" && query.componentType) input.component_type = query.componentType;
  if (query.harnessIds.length) input.harness_ids = query.harnessIds;
  if (resource === "components" && query.componentTypes.length) {
    input.component_types = query.componentTypes;
  }
  if (query.authors.length) input.authors = query.authors;
  if (query.supportTier) input.support_tier = query.supportTier;
  if (query.supportState) input.support_state = query.supportState;
  if (query.serviceDomain) input.service_domain = query.serviceDomain;
  if (query.countryCode) input.country_code = query.countryCode;
  if (query.serviceDomains?.length) input.service_domains = query.serviceDomains;
  if (query.countryCodes?.length) input.country_codes = query.countryCodes;
  if (query.updatedFrom) input.updated_from = query.updatedFrom;
  if (query.updatedTo) input.updated_to = query.updatedTo;
  if (query.resource === "all" || !query.cursor) {
    input.page = resource === "setups" ? setupsPageNumber : componentsPageNumber;
  }
  return input;
}

/**
 * Start independent catalog reads together so resource=all does not wait
 * for components before setups, and services do not precede search.
 */
export function startCatalogResourceReads(
  query: ParsedCatalogQuery,
  deps: CatalogReadDeps = defaultCatalogReadDeps,
): {
  services: Promise<Awaited<ReturnType<typeof listExternalProducts>>["items"]>;
  components: Promise<ComponentListResponse | null>;
  setups: Promise<SetupListResponse | null>;
} {
  const services = deps
    .listExternalProducts()
    .then((result) => result.items)
    .catch(() => []);
  const components =
    query.resource === "components" || query.resource === "all"
      ? deps.searchComponents(catalogSearchInput(query, "components"))
      : Promise.resolve(null);
  const setups =
    query.resource === "setups" || query.resource === "all"
      ? deps.searchSetups(catalogSearchInput(query, "setups"))
      : Promise.resolve(null);
  return { services, components, setups };
}

export async function mapPool<T, R>(
  items: readonly T[],
  concurrency: number,
  mapper: (item: T) => Promise<R>,
): Promise<R[]> {
  if (items.length === 0) {
    return [];
  }
  const limit = Math.max(1, concurrency);
  const results = new Array<R>(items.length);
  let next = 0;
  async function worker(): Promise<void> {
    while (next < items.length) {
      const index = next;
      next += 1;
      results[index] = await mapper(items[index] as T);
    }
  }
  const workers = Array.from({ length: Math.min(limit, items.length) }, () => worker());
  await Promise.all(workers);
  return results;
}

export async function loadPublisherProfiles(
  publisherIds: readonly string[],
  readProfile: (accountId: AccountId) => Promise<{
    display_name: string | null;
    avatar_url: string | null;
  }> = readPublisherProfile,
  concurrency = PUBLISHER_PROFILE_CONCURRENCY,
): Promise<Record<string, PublisherAuthorProfile>> {
  const unique = [...new Set(publisherIds)];
  const entries = await mapPool(unique, concurrency, async (publisherId) => {
    try {
      const profile = await readProfile(asAccountId(publisherId));
      return [
        publisherId,
        { displayName: profile.display_name, avatarUrl: profile.avatar_url },
      ] as const;
    } catch {
      return [publisherId, { displayName: null, avatarUrl: null }] as const;
    }
  });
  return Object.fromEntries(entries);
}
