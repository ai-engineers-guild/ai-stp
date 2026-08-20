import { getEnv } from "@/lib/env";

/**
 * API base URL for non-mock server reads.
 * The generated fetch client lives under ./generated and is regenerated via
 * `api:generate`; application code uses `http.ts` + types from types.gen.
 */
export function getApiBaseUrl(): string {
  return getEnv().AI_STP_API_BASE_URL;
}
