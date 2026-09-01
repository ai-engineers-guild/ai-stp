import type { ComponentId, CursorToken, SetupId, VersionId } from "@/lib/brands";
import { CATALOG_DEFAULT_PAGE_SIZE } from "@/lib/catalog-query";
import { publicApiGet, publicApiGetLive } from "@/lib/api/public-http";

import type {
  ComponentDetail,
  ComponentListResponse,
  ComponentVersionResponse,
  SetupDetail,
  SetupListResponse,
  SetupVersionResponse,
} from "./generated/types.gen";

export type GitHubMetadata = {
  schema_version: 1;
  stars: number | null;
  archived: boolean | null;
};

export type SetupContextBudget = {
  schema_version: 1;
  coordinate: {
    stable_id: string;
    version: string;
    passport_digest: string;
  };
  estimator: {
    profile: "ai-stp:utf8-bytes/1" | "ai-stp:unicode-chars-div4/1";
    accuracy: "exact" | "estimated";
    method: "utf8_byte_count" | "unicode_codepoints_div_4";
  };
  always_tokens: number;
  conditional_tokens: number;
  total_tokens: number;
  unavailable_components: number;
  status: "ready" | "unavailable" | "invalid_graph";
  components: Array<{
    component: {
      stable_id: string;
      version: string;
      passport_digest: string;
    };
    component_type: "instruction" | "skill" | "agent" | "command";
    loading: "always" | "conditional";
    status: "exact" | "estimated" | "unavailable";
    tokens: number | null;
    utf8_bytes: number;
    reason?: string | null;
  }>;
};

export type ComponentContextBudget = {
  schema_version: 1;
  coordinate: { stable_id: string; version: string; passport_digest: string };
  estimator: SetupContextBudget["estimator"];
  component_type: string;
  loading: "always" | "conditional" | null;
  tokens: number | null;
  utf8_bytes: number | null;
  status: "exact" | "estimated" | "unavailable" | "not_applicable";
  reason: string | null;
};

type SearchParams = {
  q?: string;
  page_size?: number;
  page?: number;
  cursor?: CursorToken;
  include_experimental?: boolean;
  tags?: ReadonlyArray<string>;
  harness_id?: string;
  component_type?: string;
  harness_ids?: ReadonlyArray<string>;
  component_types?: ReadonlyArray<string>;
  authors?: ReadonlyArray<string>;
  verified_only?: boolean;
  sort?: "relevance" | "updated_at" | "likes";
  sort_direction?: "asc" | "desc";
  support_tier?: "primary" | "beta";
  support_state?: "verified" | "stale" | "missing" | "not_verified";
  service_domain?: string;
  country_code?: string;
  service_domains?: ReadonlyArray<string>;
  country_codes?: ReadonlyArray<string>;
  updated_from?: string;
  updated_to?: string;
};

export type ExternalProductObject = {
  object_kind: "component" | "setup";
  stable_id: string;
  name: string;
};
export type ExternalProduct = {
  schema_version: 1;
  name: string;
  canonical_domain: string;
  primary_url: string;
  country_codes: string[];
  objects?: ExternalProductObject[];
};
export type Country = {
  schema_version: 1;
  code: string;
  services_count: number;
  objects_count: number;
  services: ExternalProduct[];
  objects: ExternalProductObject[];
};

export async function listExternalProducts(): Promise<{
  schema_version: 1;
  items: ExternalProduct[];
}> {
  return publicApiGet("/v1/catalog/services");
}

export async function readExternalProduct(domain: string): Promise<ExternalProduct> {
  return publicApiGet(`/v1/catalog/services/${encodeURIComponent(domain)}`);
}

export async function readCountry(code: string): Promise<Country> {
  return publicApiGet(`/v1/catalog/countries/${encodeURIComponent(code)}`);
}

export async function searchComponents(params: SearchParams = {}): Promise<ComponentListResponse> {
  return publicApiGet<ComponentListResponse>("/v1/catalog/components", {
    query: {
      q: params.q,
      page_size: params.page_size ?? CATALOG_DEFAULT_PAGE_SIZE,
      page: params.page,
      cursor: params.cursor,
      include_experimental: params.include_experimental ?? true,
      tags: params.tags && params.tags.length > 0 ? [...params.tags] : undefined,
      harness_id: params.harness_id,
      component_type: params.component_type,
      harness_ids: params.harness_ids ? [...params.harness_ids] : undefined,
      component_types: params.component_types ? [...params.component_types] : undefined,
      authors: params.authors ? [...params.authors] : undefined,
      verified_only: params.verified_only,
      sort: params.sort,
      sort_direction: params.sort_direction,
      support_tier: params.support_tier,
      support_state: params.support_state,
      service_domain: params.service_domain,
      country_code: params.country_code,
      service_domains: params.service_domains ? [...params.service_domains] : undefined,
      country_codes: params.country_codes ? [...params.country_codes] : undefined,
      updated_from: params.updated_from,
      updated_to: params.updated_to,
    },
  });
}

export async function searchSetups(params: SearchParams = {}): Promise<SetupListResponse> {
  return publicApiGet<SetupListResponse>("/v1/catalog/setups", {
    query: {
      q: params.q,
      page_size: params.page_size ?? CATALOG_DEFAULT_PAGE_SIZE,
      page: params.page,
      cursor: params.cursor,
      include_experimental: params.include_experimental ?? true,
      tags: params.tags && params.tags.length > 0 ? [...params.tags] : undefined,
      harness_id: params.harness_id,
      harness_ids: params.harness_ids ? [...params.harness_ids] : undefined,
      authors: params.authors ? [...params.authors] : undefined,
      verified_only: params.verified_only,
      sort: params.sort,
      sort_direction: params.sort_direction,
      support_tier: params.support_tier,
      support_state: params.support_state,
      service_domain: params.service_domain,
      country_code: params.country_code,
      service_domains: params.service_domains ? [...params.service_domains] : undefined,
      country_codes: params.country_codes ? [...params.country_codes] : undefined,
      updated_from: params.updated_from,
      updated_to: params.updated_to,
    },
  });
}

export type CatalogRelationService = {
  name: string;
  canonical_domain: string;
  primary_url: string;
  country_codes: string[];
};

export function catalogRelations(detail: { country_codes?: unknown; services?: unknown }): {
  country_codes: string[];
  services: CatalogRelationService[];
} {
  const country_codes = Array.isArray(detail.country_codes)
    ? detail.country_codes.filter((item): item is string => typeof item === "string")
    : [];
  const services = Array.isArray(detail.services)
    ? detail.services.flatMap((item) => {
        if (!item || typeof item !== "object") return [];
        const row = item as Record<string, unknown>;
        if (
          typeof row.name !== "string" ||
          typeof row.canonical_domain !== "string" ||
          typeof row.primary_url !== "string"
        ) {
          return [];
        }
        return [
          {
            name: row.name,
            canonical_domain: row.canonical_domain,
            primary_url: row.primary_url,
            country_codes: Array.isArray(row.country_codes)
              ? row.country_codes.filter((code): code is string => typeof code === "string")
              : [],
          },
        ];
      })
    : [];
  return { country_codes, services };
}

export async function readComponent(stableId: ComponentId): Promise<ComponentDetail> {
  return publicApiGet<ComponentDetail>(`/v1/catalog/components/${stableId}`);
}

export async function readSetup(stableId: SetupId): Promise<SetupDetail> {
  return publicApiGet<SetupDetail>(`/v1/catalog/setups/${stableId}`);
}

export async function readComponentVersion(
  stableId: ComponentId,
  version: VersionId,
): Promise<ComponentVersionResponse> {
  return publicApiGet<ComponentVersionResponse>(
    `/v1/catalog/components/${stableId}/versions/${version}`,
  );
}

export async function readSetupVersion(
  stableId: SetupId,
  version: VersionId,
): Promise<SetupVersionResponse> {
  return publicApiGet<SetupVersionResponse>(`/v1/catalog/setups/${stableId}/versions/${version}`);
}

export async function readComponentGithubMetadata(
  stableId: ComponentId,
  version: VersionId,
): Promise<GitHubMetadata> {
  return publicApiGetLive<GitHubMetadata>(
    `/v1/catalog/components/${stableId}/versions/${version}/github-metadata`,
  );
}

export async function readSetupGithubMetadata(
  stableId: SetupId,
  version: VersionId,
): Promise<GitHubMetadata> {
  return publicApiGetLive<GitHubMetadata>(
    `/v1/catalog/setups/${stableId}/versions/${version}/github-metadata`,
  );
}

export async function readSetupContextBudget(
  stableId: SetupId,
  version: VersionId,
): Promise<SetupContextBudget> {
  return publicApiGetLive<SetupContextBudget>(
    `/v1/catalog/setups/${stableId}/versions/${version}/context-budget`,
  );
}

export async function readComponentContextBudget(
  stableId: ComponentId,
  version: VersionId,
): Promise<ComponentContextBudget> {
  return publicApiGetLive<ComponentContextBudget>(
    `/v1/catalog/components/${stableId}/versions/${version}/context-budget`,
  );
}
