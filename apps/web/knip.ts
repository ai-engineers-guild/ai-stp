import type { KnipConfig } from "knip";

const config: KnipConfig = {
  entry: [
    // Invoked by the native browser check's Bash entry point.
    "scripts/ensure-chrome.mjs",
    // The generated SDK is a complete schema projection, including unused endpoints.
    "src/lib/api/generated/index.ts",
    // Storybook's viteFinal and the feature-profile resolver select these at runtime.
    "src/stories/shims/*.{ts,tsx}",
    "src/lib/features/disabled-public-surface.ts",
  ],
  // eslint-plugin-import loads this from the `import/resolver: { node: true }` setting.
  ignoreDependencies: ["eslint-import-resolver-node"],
};

export default config;
