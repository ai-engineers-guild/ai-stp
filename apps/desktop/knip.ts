import type { KnipConfig } from "knip";

const config: KnipConfig = {
  entry: [
    // Canonical projections retain the complete wire and native contract surfaces.
    "src/generated/{cli,native}.ts",
    // The root Just generators invoke these outside package.json scripts.
    "scripts/generate-{contracts,fonts,messages,theme}.mjs",
  ],
  treatConfigHintsAsErrors: true,
};

export default config;
