import path from "node:path";

import { defineConfig } from "vitest/config";

/**
 * SPEC-034 changed-scope coverage gate.
 *
 * This is intentionally separate from the honest repository-wide coverage
 * report in vitest.config.ts. It gates catalog/search production modules
 * changed by SPEC-034; Markdown has its own repository-wide unit coverage.
 */
export default defineConfig({
  esbuild: { jsx: "automatic" },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./tests/setup.ts"],
    include: [
      "tests/unit/catalog-query.test.ts",
      "tests/unit/markdown-render.test.ts",
      "tests/component/catalog-search-form.test.tsx",
      "tests/component/searchable-multi-select.test.tsx",
      "tests/component/catalog-filters.test.tsx",
      "tests/component/catalog-results.test.tsx",
      "tests/component/object-card.test.tsx",
    ],
    css: false,
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: [
        "src/lib/catalog-query.ts",
        "src/components/molecules/searchable-multi-select.tsx",
        "src/components/organisms/catalog-search-form.tsx",
        "src/components/organisms/catalog-filters.tsx",
        "src/components/organisms/catalog-filter-panel.tsx",
        "src/components/organisms/catalog-results.tsx",
        "src/components/organisms/object-card.tsx",
      ],
      thresholds: {
        statements: 95,
        branches: 95,
        functions: 95,
        lines: 95,
      },
    },
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
