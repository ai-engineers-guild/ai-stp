import type { KnipConfig } from "knip";

const config: KnipConfig = {
  entry: [
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
