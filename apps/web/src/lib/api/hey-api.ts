/**
 * Runtime config hook for @hey-api/client-fetch generation.
 * Referenced by openapi-ts `runtimeConfigPath`; kept stable for regeneration.
 */
export const createClientConfig = <T extends Record<string, unknown>>(config: T): T => ({
  ...config,
});
