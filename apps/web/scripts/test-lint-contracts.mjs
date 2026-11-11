import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";

const root = fileURLToPath(new URL("../", import.meta.url));
const directories = [];
const cases = [];
let checks = 0;

async function ownDirectory(parent) {
  const directory = await mkdtemp(path.join(parent, "ai-stp-lint-contract-"));
  directories.push(directory);
  return directory;
}
async function sourceCase(directory, name, code, rule) {
  const filename = path.join(directory, name + ".tsx");
  await writeFile(filename, code);
  cases.push({ filename, rule });
}
try {
  const boundaries = [
    ["components/atoms", "components/molecules/form-dialog"],
    ["components/molecules", "components/organisms/object-card"],
    ["components/organisms", "components/layouts/app-shell"],
    ["components/layouts", "app/[locale]/layout"],
  ];
  for (const [layer, higher] of boundaries) {
    const directory = await ownDirectory(path.join(root, "src", layer));
    const relative = path
      .relative(directory, path.join(root, "src", higher))
      .split(path.sep)
      .join("/");
    for (const [kind, specifier] of [
      ["alias", "@/" + higher],
      ["relative", relative],
    ]) {
      await sourceCase(
        directory,
        kind + "-import",
        "import * as higher from " + JSON.stringify(specifier) + "; export { higher };",
        "import-x/no-restricted-paths",
      );
      await sourceCase(
        directory,
        kind + "-export",
        "export * from " + JSON.stringify(specifier) + ";",
        "import-x/no-restricted-paths",
      );
    }
  }
  const atoms = directories[0];
  await sourceCase(atoms, "same-layer", 'export { Input } from "@/components/atoms/input";');
  await sourceCase(
    directories[2],
    "lower-layer",
    'export { Button } from "@/components/atoms/button";',
  );
  for (const [name, code, rule] of [
    [
      "hooks",
      'import { useState } from "react"; export function Invalid({ enabled }: { enabled: boolean }) { if (enabled) { const [value] = useState(0); return <span>{value}</span>; } return null; }',
      "react-hooks/rules-of-hooks",
    ],
    ["unsafe", 'export const value = JSON.parse("{}");', "@typescript-eslint/no-unsafe-assignment"],
    [
      "deprecated",
      "/** @deprecated Use the supported API. */ export function obsolete() {} obsolete();",
      "@typescript-eslint/no-deprecated",
    ],
    ["color", 'export const color = "#123456";', "no-restricted-syntax"],
    ["copy", "export const Copy = () => <button>Untranslated</button>;", "no-restricted-syntax"],
  ]) {
    await sourceCase(atoms, name, code, rule);
  }
  // Independent files share one program; replacing an imported UI primitive
  // repeatedly invalidates the application's complete TypeScript graph.
  console.log("Checking " + cases.length + " ESLint contracts in one program.");
  const eslint = new ESLint({ cwd: root });
  const results = await eslint.lintFiles(cases.map(({ filename }) => filename));
  assert.equal(results.length, cases.length);
  const byFilename = new Map(
    results.map((result) => [path.resolve(result.filePath), result.messages]),
  );
  for (const { filename, rule } of cases) {
    const messages = byFilename.get(path.resolve(filename));
    assert(messages, filename + ": missing lint result");
    assert(!messages.some((message) => message.fatal), JSON.stringify(messages));
    if (rule) {
      assert(
        messages.some((message) => message.ruleId === rule && message.severity === 2),
        filename + ": missing " + rule + ": " + JSON.stringify(messages),
      );
    } else {
      assert.deepEqual(messages, [], filename + ": valid source was rejected");
    }
    checks += 1;
  }
  console.log("ESLint contracts passed.");
  const directory = await ownDirectory(tmpdir());
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
        "--report-unused-disable-directives",
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
  await checkOxlint("export const Row = () => <tr tabIndex={0} />;", [
    "jsx-a11y(no-noninteractive-tabindex)",
  ]);
  await checkOxlint(
    "export const Row = () => <tr\n tabIndex={0} // oxlint-disable-line jsx-a11y/no-noninteractive-tabindex -- Focusable data rows support keyboard selection.\n />;",
    [],
  );
} finally {
  for (const directory of directories.toReversed()) {
    await rm(directory, { recursive: true, force: true });
  }
}
console.log("Lint contracts: " + checks + " checks passed.");
