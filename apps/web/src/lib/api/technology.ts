import { privateApiRequest } from "@/lib/api/http";

import type { TechnologyLandscapeView } from "./generated/types.gen";

export const LANDSCAPE_FILTER_KEYS = [
  "category_id",
  "technology_id",
  "project_id",
  "team_id",
  "lifecycle",
  "adoption",
  "context",
  "review",
  "freshness",
  "include_history",
  "include_inactive",
  "offset",
  "limit",
  "project_offset",
  "project_limit",
] as const;

export function landscapeFilters(params: Record<string, string | string[] | undefined>) {
  return Object.fromEntries(
    LANDSCAPE_FILTER_KEYS.flatMap((key) => {
      const value = params[key];
      return typeof value === "string" && value ? [[key, value]] : [];
    }),
  );
}

export async function readTechnologyLandscape(
  sessionToken: string,
  organizationId: string,
  filters: Record<string, string>,
): Promise<TechnologyLandscapeView> {
  return privateApiRequest<TechnologyLandscapeView>(
    `/v1/corporate/organizations/${organizationId}/technology-landscape`,
    { sessionToken, query: filters },
  );
}
