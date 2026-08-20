import { defineConfig } from "@hey-api/openapi-ts";

/**
 * Generates the typed contract client from the frozen #71 OpenAPI document.
 * Output is a build artifact: never hand-edit files under src/lib/api/generated.
 */
export default defineConfig({
  input: "../../schemas/v1/openapi.json",
  output: {
    path: "src/lib/api/generated",
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
