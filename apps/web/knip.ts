import type { KnipConfig } from "knip";

const config: KnipConfig = {
  entry: [
    // Invoked by the native browser check's Bash entry point.
    "scripts/ensure-chrome.mjs",
    // The generated SDK is a complete schema projection, including unused endpoints.
    "src/lib/api/generated/**/*.ts",
    "src/lib/generated/cli-copy.ts",
    "src/lib/generated/deep-link-corpus.ts",
    "src/lib/cli-copy.ts",
    // The canonical theme and fixture identities are retained public contracts.
    "src/theme/index.ts",
    "src/theme/tokens.ts",
    "src/mocks/fixtures/catalog-ids.ts",
    // Storybook's viteFinal and the feature-profile resolver select these at runtime.
    "src/stories/shims/*.{ts,tsx}",
    "src/lib/features/disabled-public-surface.ts",
  ],
};

export default config;
