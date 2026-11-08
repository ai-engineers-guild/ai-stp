/**
 * Runtime config hook for the generated bundled Fetch client.
 * Referenced by openapi-ts `runtimeConfigPath`; kept stable for regeneration.
 */
export const createClientConfig = <T extends Record<string, unknown>>(config: T): T => ({
  ...config,
});
