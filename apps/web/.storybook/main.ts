import path from "node:path";
import { fileURLToPath } from "node:url";

import type { StorybookConfig } from "@storybook/react-vite";
import { mergeConfig } from "vite";

const rootDir = path.dirname(fileURLToPath(import.meta.url));
const appDir = path.resolve(rootDir, "..");

const config: StorybookConfig = {
  stories: ["../src/**/*.mdx", "../src/**/*.stories.@(ts|tsx)"],
  addons: ["@storybook/addon-essentials", "@storybook/addon-a11y", "@storybook/addon-themes"],
  framework: {
    name: "@storybook/react-vite",
    options: {},
  },
  docs: {
    autodocs: "tag",
  },
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
