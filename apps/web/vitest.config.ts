import path from "node:path";

import { defineConfig } from "vitest/config";

export default defineConfig({
  esbuild: {
    jsx: "automatic",
  },
  test: {
    environment: "jsdom",
    globals: false,
    // Type-aware Next.js module transforms can starve the default worker-per-core
    // pool on Windows and make otherwise instant tests hit Vitest's timeout.
    // Keep bounded parallelism so the same suite is deterministic locally and in CI.
    maxWorkers: 4,
    // The other half of that answer, and it was missing. Bounding the pool made
    // the suite deterministic; it did not make Windows fast. `ADR-0116` measured
    // this suite at 176-233s there against 47s on macOS, so a 5s per-test cap
    // gives a test that takes one second locally no margin at all on the slowest
    // platform we support — it passes until something costs it another 8%.
    //
    // That is what happened: `catalog-filters` "keeps country and service
    // filters linked" runs in ~1.1s here and timed out on Windows after an
    // effect was added to a component it renders. The cap was calibrated on the
    // fast platform, which is the defect; raising it is the correction.
    //
    // Finite on purpose. A genuine hang must still fail the job rather than
    // hold a runner until the job's own ceiling.
    testTimeout: 20_000,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/unit/**/*.{test,spec}.{ts,tsx}", "tests/component/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["node_modules", ".next", "tests/e2e", "src/stories/**", ".storybook/**"],
    css: false,
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/lib/api/generated/**",
        "src/mocks/**",
        "src/stories/**",
        "**/*.d.ts",
        "src/app/**/layout.tsx",
      ],
      // Floors track decision logic we unit-test (lib/api/auth/query). Pages stay
      // in e2e. Under v8, unimported files report 0% lines but 100% branches —
      // so only `lines`/`statements` are honest floors; raise them when Tier A
      // lib coverage grows, not when pages are added.
      // Measured after closeout unit suite (api-errors, catalog-client, logout,
      // session expiry): lines/statements ~23.8%, branches ~73%, functions ~58%.
      thresholds: {
        lines: 20,
        functions: 50,
        branches: 65,
        statements: 20,
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
