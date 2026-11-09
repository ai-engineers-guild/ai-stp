import { afterEach, expect, it } from "vitest";
import {
  cpSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { IntlMessageFormat } from "intl-messageformat";
import { parameters } from "./message-parameters.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const temporary = [];
afterEach(() => {
  for (const directory of temporary.splice(0))
    rmSync(directory, { recursive: true, force: true });
});

function fixture() {
  const directory = mkdtempSync(path.join(tmpdir(), "desktop-messages-"));
  temporary.push(directory);
  cpSync(path.join(root, "src"), path.join(directory, "src"), {
    recursive: true,
  });
  cpSync(path.join(root, "scripts"), path.join(directory, "scripts"), {
    recursive: true,
  });
  symlinkSync(
    path.join(root, "node_modules"),
    path.join(directory, "node_modules"),
    process.platform === "win32" ? "junction" : "dir",
  );
  return directory;
}
function check(directory) {
  return spawnSync(
    process.execPath,
    [path.join(directory, "scripts/check-messages.mjs")],
    { cwd: directory, encoding: "utf8" },
  );
}

it.each([
  ["visible JSX", "<div>Untranslated interface</div>"],
  ["accessible name", '<button aria-label="Untranslated action" />'],
  ["conditional text", '<div>{true ? "Untranslated state" : null}</div>'],
  // biome-ignore lint/suspicious/noTemplateCurlyInString: This fixture is source text parsed by the message guard.
  ["interpolated text", "<div>{`Untranslated ${42} items`}</div>"],
])("rejects %s outside the catalog", (_, source) => {
  const directory = fixture();
  writeFileSync(
    path.join(directory, "src/Untranslated.tsx"),
    `export default () => (${source});\n`,
  );
  const result = check(directory);
  expect(result.status).not.toBe(0);
  expect(result.stderr).toContain("Desktop text bypasses its catalog");
});

it.each(["missing key", "argument kind"])(
  "rejects a translated %s mismatch",
  (failure) => {
    const directory = fixture();
    const file = path.join(directory, "src/locales/ar.json");
    const messages = JSON.parse(readFileSync(file, "utf8"));
    if (failure === "missing key") delete messages[Object.keys(messages)[0]];
    else messages["debug.ms"] = "{duration}";
    writeFileSync(file, JSON.stringify(messages));
    const result = check(directory);
    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain(
      failure === "missing key"
        ? "message keys differ"
        : "argument names or kinds differ",
    );
  },
);

it("formats every packaged message, including plural and selector branches", () => {
  const configuration = JSON.parse(
    readFileSync(path.join(root, "src/localization.json"), "utf8"),
  );
  for (const locale of Object.keys(configuration.languages)) {
    const messages = JSON.parse(
      readFileSync(path.join(root, `src/locales/${locale}.json`), "utf8"),
    );
    for (const [key, message] of Object.entries(messages)) {
      const formatter = new IntlMessageFormat(message, locale, undefined, {
        ignoreTag: true,
      });
      const ast = formatter.getAst();
      const values = Object.fromEntries(
        [...parameters(ast)].map(([name, kind]) => [
          name,
          kind === "number"
            ? 0
            : kind === "Date | number"
              ? new Date(0)
              : "other",
        ]),
      );
      const variants = [values];
      function branches(nodes) {
        for (const node of nodes) {
          if (node.type === 5)
            for (const choice of Object.keys(node.options))
              variants.push({ ...values, [node.value]: choice });
          if (node.type === 6)
            for (const count of [0, 1, 2, 3, 5, 11, 101])
              variants.push({ ...values, [node.value]: count });
          if (node.options)
            for (const option of Object.values(node.options))
              branches(option.value);
        }
      }
      branches(ast);
      for (const variant of variants)
        expect(
          () => formatter.format(variant),
          `${locale}:${key}`,
        ).not.toThrow();
    }
  }
});
