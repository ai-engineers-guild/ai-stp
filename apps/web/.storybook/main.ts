import path from "node:path";
import { fileURLToPath } from "node:url";

import type { StorybookConfig } from "@storybook/react-vite";
import { mergeConfig } from "vite";

const rootDir = path.dirname(fileURLToPath(import.meta.url));
const appDir = path.resolve(rootDir, "..");

const config: StorybookConfig = {
  stories: ["../src/**/*.mdx", "../src/**/*.stories.@(ts|tsx)"],
  // `addon-essentials` is gone from Storybook 9 onward: controls, actions,
  // viewport, backgrounds and docs are core now, so listing it would fail to
  // resolve rather than add anything.
  // `addon-docs` is listed on its own now. It used to arrive inside
  // `addon-essentials`, which Storybook 9 dissolved into the core — except
  // for docs, which stayed an addon and therefore has to be asked for.
  addons: ["@storybook/addon-docs", "@storybook/addon-a11y", "@storybook/addon-themes"],
  framework: {
    name: "@storybook/react-vite",
    options: {},
  },
  // `docs.autodocs` went with the same release. Tag-driven autodocs is the
  // default now, which is what `"tag"` selected, so the behaviour is
  // unchanged by dropping the option.
  async viteFinal(config) {
    // Dynamic imports: Storybook evaluates main.ts via CJS interop; package
    // exports for Vite plugins are ESM-only.
    const [{ default: react }, { default: tailwindcss }] = await Promise.all([
      import("@vitejs/plugin-react"),
      import("@tailwindcss/vite"),
    ]);
    return mergeConfig(config, {
      plugins: [react(), tailwindcss()],
      resolve: {
        // Specific shims first — a bare "@" alias would swallow "@/actions/*".
        alias: [
          {
            find: "next/navigation",
            replacement: path.resolve(appDir, "src/stories/shims/next-navigation.ts"),
          },
          {
            find: "@/lib/i18n/navigation",
            replacement: path.resolve(appDir, "src/stories/shims/i18n-navigation.tsx"),
          },
          {
            find: "@/actions/account",
            replacement: path.resolve(appDir, "src/stories/shims/actions-account.ts"),
          },
          {
            find: "@/actions/devices",
            replacement: path.resolve(appDir, "src/stories/shims/actions-devices.ts"),
          },
          {
            find: "@",
            replacement: path.resolve(appDir, "src"),
          },
        ],
      },
    });
  },
};

export default config;
