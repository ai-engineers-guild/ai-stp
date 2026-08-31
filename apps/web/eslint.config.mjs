import path from "node:path";
import { fileURLToPath } from "node:url";

import js from "@eslint/js";
import importPlugin from "eslint-plugin-import";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import("eslint").Linter.Config[]} */
export default [
  {
    ignores: [
      ".next/**",
      ".next-*/**",
      "node_modules/**",
      "src/lib/api/generated/**",
      "public/**",
      "coverage/**",
      "playwright-report/**",
      "test-results/**",
      "storybook-static/**",
      ".storybook/**",
      "src/stories/**",
      "scripts/**",
      "bun.lock",
      "next-env.d.ts",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  ...tseslint.configs.strictTypeChecked,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: __dirname,
      },
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: {
      import: importPlugin,
      react,
      "react-hooks": reactHooks,
      "jsx-a11y": jsxA11y,
    },
    settings: {
      react: { version: "detect" },
      "import/resolver": {
        node: true,
      },
    },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs["jsx-runtime"].rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.configs.recommended.rules,
      "react/prop-types": "off",
      "react/react-in-jsx-scope": "off",
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unsafe-argument": "error",
      "@typescript-eslint/no-unsafe-assignment": "error",
      "@typescript-eslint/no-unsafe-call": "error",
      "@typescript-eslint/no-unsafe-member-access": "error",
      "@typescript-eslint/no-unsafe-return": "error",
      // next-intl still documents setRequestLocale for App Router static rendering.
      "@typescript-eslint/no-deprecated": "off",
      "@typescript-eslint/no-unnecessary-type-parameters": "off",
      "@typescript-eslint/restrict-template-expressions": [
        "error",
        { allowNumber: true, allowBoolean: true },
      ],
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports", fixStyle: "inline-type-imports" },
      ],
      "no-restricted-syntax": [
        "error",
        {
          selector: "Literal[value=/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/]",
          message: "Hard-coded hex colors are forbidden. Use semantic theme tokens (REQ-2214).",
        },
        {
          selector: "Literal[value=/^rgb(a)?\\(/i]",
          message: "Hard-coded rgb colors are forbidden. Use semantic theme tokens (REQ-2214).",
        },
        {
          selector: "Literal[value=/^hsl(a)?\\(/i]",
          message: "Hard-coded hsl colors are forbidden. Use semantic theme tokens (REQ-2214).",
        },
      ],
      "max-lines": ["error", { max: 450, skipBlankLines: true, skipComments: true }],
      "max-lines-per-function": ["error", { max: 160, skipBlankLines: true, skipComments: true }],
      complexity: ["error", 25],
      "import/no-restricted-paths": [
        "error",
        {
          zones: [
            {
              target: "./src/components/atoms",
              from: [
                "./src/components/molecules",
                "./src/components/organisms",
                "./src/components/layouts",
                "./src/app",
              ],
              message: "atoms may not import higher atomic layers",
            },
            {
              target: "./src/components/molecules",
              from: ["./src/components/organisms", "./src/components/layouts", "./src/app"],
              message: "molecules may not import higher atomic layers",
            },
            {
              target: "./src/components/organisms",
              from: ["./src/components/layouts", "./src/app"],
              message: "organisms may not import layouts or app routes",
            },
            {
              target: "./src/components/layouts",
              from: ["./src/app"],
              message: "layouts may not import app routes",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/app/**/*.{ts,tsx}", "src/components/**/*.{ts,tsx}"],
    ignores: ["src/stories/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "Literal[value=/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/]",
          message: "Hard-coded hex colors are forbidden. Use semantic theme tokens (REQ-2214).",
        },
        {
          selector: "Literal[value=/^rgb(a)?\\(/i]",
          message: "Hard-coded rgb colors are forbidden. Use semantic theme tokens (REQ-2214).",
        },
        {
          selector: "Literal[value=/^hsl(a)?\\(/i]",
          message: "Hard-coded hsl colors are forbidden. Use semantic theme tokens (REQ-2214).",
        },
        {
          selector: "JSXText[value=/[A-Za-z\\u0410-\\u042f\\u0430-\\u044f]/]",
          message: "User-facing JSX text must use next-intl (REQ-2203).",
        },
        {
          selector:
            "JSXAttribute[name.name=/^(placeholder|alt|title|aria-label|aria-description)$/] > Literal[value=/[A-Za-z\\u0410-\\u042f\\u0430-\\u044f]/]",
          message: "User-facing attribute strings must use next-intl (REQ-2203).",
        },
      ],
    },
  },
  {
    files: ["**/*.{test,spec}.{ts,tsx}", "tests/**/*.{ts,tsx}"],
    rules: {
      "max-lines-per-function": "off",
      complexity: "off",
      "@typescript-eslint/no-misused-spread": "off",
    },
  },
  {
    files: ["**/*.{mjs,js}"],
    ...tseslint.configs.disableTypeChecked,
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
];
