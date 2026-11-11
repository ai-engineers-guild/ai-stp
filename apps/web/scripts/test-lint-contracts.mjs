import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ESLint } from "eslint";

const root = fileURLToPath(new URL("../", import.meta.url));
const eslint = new ESLint({ cwd: root });
let checks = 0;
async function checkEslint(code, filename, expectedRule) {
  const results = await eslint.lintText(code, { filePath: path.join(root, "src", filename) });
  const messages = results.flatMap((result) => result.messages);
  assert(!messages.some((message) => message.fatal), JSON.stringify(messages));
  if (expectedRule) {
    assert(
      messages.some((message) => message.ruleId === expectedRule && message.severity === 2),
      filename + ": missing " + expectedRule + ": " + JSON.stringify(messages),
    );
  } else {
    assert.deepEqual(messages, [], filename + ": valid source was rejected");
  }
  checks += 1;
}
const boundaries = [
  ["components/atoms/button.tsx", "components/molecules/form-dialog"],
  ["components/molecules/form-dialog.tsx", "components/organisms/object-card"],
  ["components/organisms/object-card.tsx", "components/layouts/app-shell"],
  ["components/layouts/app-shell.tsx", "app/[locale]/layout"],
];
for (const [filename, higher] of boundaries) {
  const relative = path.posix.relative(path.posix.dirname(filename), higher);
  for (const specifier of ["@/" + higher, relative.startsWith(".") ? relative : "./" + relative]) {
    await checkEslint(
      "import * as higher from " + JSON.stringify(specifier) + "; export { higher };",
      filename,
      "import-x/no-restricted-paths",
    );
    await checkEslint(
      "export * from " + JSON.stringify(specifier) + ";",
      filename,
      "import-x/no-restricted-paths",
    );
  }
}
await checkEslint(
  'export { Button } from "@/components/atoms/button";',
  "components/organisms/object-card.tsx",
);
await checkEslint('export { Input } from "./input";', "components/atoms/button.tsx");
for (const [code, rule] of [
  [
    'import { useState } from "react"; export function Invalid({ enabled }: { enabled: boolean }) { if (enabled) { const [value] = useState(0); return <span>{value}</span>; } return null; }',
    "react-hooks/rules-of-hooks",
  ],
  ['export const value = JSON.parse("{}");', "@typescript-eslint/no-unsafe-assignment"],
  [
    "/** @deprecated Use the supported API. */ function obsolete() {} obsolete();",
    "@typescript-eslint/no-deprecated",
  ],
  ['export const color = "#123456";', "no-restricted-syntax"],
  ["export const Copy = () => <button>Untranslated</button>;", "no-restricted-syntax"],
]) {
  await checkEslint(code, "components/atoms/button.tsx", rule);
}
const directory = await mkdtemp(path.join(tmpdir(), "ai-stp-lint-contract-"));
try {
  const filename = path.join(directory, "ui.tsx");
  async function checkOxlint(code, expectedRules) {
    await writeFile(filename, code);
    const result = spawnSync(
      process.execPath,
      [
        path.join(root, "node_modules/oxlint/bin/oxlint"),
        "--config",
        path.join(root, ".oxlintrc.json"),
        "--no-ignore",
        "--format",
        "json",
        filename,
      ],
      { cwd: root, encoding: "utf8" },
    );
    assert.ifError(result.error);
    assert.equal(result.signal, null, result.stderr);
    const report = JSON.parse(result.stdout);
    const codes = report.diagnostics.map((diagnostic) => diagnostic.code);
    if (expectedRules.length === 0) {
      assert.equal(result.status, 0, result.stdout + result.stderr);
      assert.deepEqual(codes, []);
    } else {
      assert.equal(result.status, 1, result.stdout + result.stderr);
      for (const rule of expectedRules) assert(codes.includes(rule), rule + ": " + result.stdout);
    }
    checks += 1;
  }
  await checkOxlint(
    'export const Image = ({ label }: { label: string }) => <img src="/image.png" alt={label} />;',
    [],
  );
  await checkOxlint(
    'import React from "react"; export function Invalid() { return ["x"].map(value => <img src={value} />); } export class Legacy extends React.Component { componentWillMount() {} render() { return null; } }',
    ["jsx-a11y(alt-text)", "react(jsx-key)", "react(no-unsafe)"],
  );
} finally {
  await rm(directory, { recursive: true, force: true });
}
console.log("Lint contracts: " + checks + " checks passed.");
