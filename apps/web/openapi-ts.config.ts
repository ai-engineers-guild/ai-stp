import { defineConfig } from "@hey-api/openapi-ts";

/**
 * Generates the typed contract client from the frozen #71 OpenAPI document.
 * Output is a build artifact: never hand-edit files under src/lib/api/generated.
 */
export default defineConfig({
  input: "../../schemas/v1/openapi.json",
  output: {
    // `scripts/api-check.mjs` redirects this to a temporary directory so drift
    // is measured against a fresh render, not a second copy of the output.
    path: process.env.AI_STP_WEB_API_OUT ?? "src/lib/api/generated",
    postProcess: [],
  },
  plugins: [
    {
      name: "@hey-api/typescript",
      enums: "javascript",
    },
    {
      name: "@hey-api/client-fetch",
      runtimeConfigPath: "./src/lib/api/hey-api.ts",
    },
    "@hey-api/sdk",
  ],
});
