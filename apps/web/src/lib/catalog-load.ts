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

export type CatalogReadScope = {
  sessionToken?: string;
  organizationId?: string;
};

const defaultCatalogReadDeps: CatalogReadDeps = {
  listExternalProducts,
  searchComponents,
  searchSetups,
};

type CatalogSearchInput = NonNullable<Parameters<typeof searchComponents>[0]>;

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
    verification: query.verification,
    verified_only: query.verifiedOnly,
    sort: query.sort,
    sort_direction: query.sortDirection,
    page_size: query.pageSize,
    include_experimental: query.includeExperimental,
  };
  if (query.minSafetyPercent !== undefined) {
    input.min_safety_percent = query.minSafetyPercent;
  }
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
  if (query.teamIds?.length) input.team_ids = query.teamIds;
  if (query.projectIds?.length) input.project_ids = query.projectIds;
  if (query.technologyIds?.length) input.technology_ids = query.technologyIds;
  if (query.categoryIds?.length) input.category_ids = query.categoryIds;
  if (query.ownerIds?.length) input.owner_ids = query.ownerIds;
  if (query.maintainerIds?.length) input.maintainer_ids = query.maintainerIds;
  if (query.assignment) input.assignment = query.assignment;
  if (query.corporateVerified !== undefined) input.corporate_verified = query.corporateVerified;
  if (resource === "setups" && query.familyId) input.family_id = query.familyId;
  if (resource === "setups" && query.familyAlignment) {
    input.family_alignment = query.familyAlignment;
  }
  if (resource === "setups" && query.memberHarnessId) {
    input.member_harness_id = query.memberHarnessId;
  }
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
  scope: CatalogReadScope = {},
): {
  services: Promise<Awaited<ReturnType<typeof listExternalProducts>>["items"]>;
  components: Promise<ComponentListResponse | null>;
  setups: Promise<SetupListResponse | null>;
} {
  const services = deps
    .listExternalProducts()
    .then((result) => result.items)
    .catch(() => []);
  const scopedInput = (resource: "components" | "setups") => ({
    ...catalogSearchInput(query, resource),
    ...(scope.sessionToken ? { sessionToken: scope.sessionToken } : {}),
    ...(scope.organizationId ? { organization_id: scope.organizationId } : {}),
  });
  const components =
    query.resource === "components" || query.resource === "all"
      ? deps.searchComponents(scopedInput("components"))
      : Promise.resolve(null);
  const setups =
    query.resource === "setups" || query.resource === "all"
      ? deps.searchSetups(scopedInput("setups"))
      : Promise.resolve(null);
  // Observe immediately: callers may await optional facets before search results.
  // Keep the original rejected promises so failures still reach their error panel.
  void components.catch(() => undefined);
  void setups.catch(() => undefined);
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
