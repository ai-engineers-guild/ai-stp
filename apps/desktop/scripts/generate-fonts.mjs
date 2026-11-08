import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { format } from "prettier";

const configuration = JSON.parse(
  readFileSync(new URL("../font-assets.json", import.meta.url), "utf8"),
);
const output = new Map();
const rules = [
  "/* Generated from pinned Fontsource assets; WOFF2 only. Run just desktop-gen. */",
];
for (const name of configuration.packages) {
  const directory = new URL(`../node_modules/${name}/`, import.meta.url);
  const license = readFileSync(new URL("LICENSE", directory), "utf8");
  output.set(
    new URL(
      `../public/fonts/${name.split("/").at(-1)}-LICENSE.txt`,
      import.meta.url,
    ),
    license,
  );
  for (const weight of configuration.weights) {
    const css = readFileSync(new URL(`${weight}.css`, directory), "utf8");
    for (const rule of css.matchAll(/@font-face\s*\{[^}]+\}/g)) {
      const files = [...rule[0].matchAll(/url\(([^)]+\.woff2)\)/g)];
      if (files.length !== 1)
        throw new Error(`Expected one WOFF2 source in ${name}/${weight}`);
      const relative = files[0][1].replace(/^\.\//, "");
      // Fail generation when the lockfile's package does not contain its declared asset.
      readFileSync(new URL(relative, directory));
      rules.push(
        rule[0].replace(
          /src:[^;]+;/,
          `src: url("../../node_modules/${name}/${relative}") format("woff2");`,
        ),
      );
    }
  }
}
output.set(
  new URL("../src/generated/fonts.css", import.meta.url),
  await format(rules.join("\n"), { parser: "css" }),
);
for (const [target, expected] of output) {
  if (process.argv.includes("--check")) {
    if (readFileSync(target, "utf8") !== expected)
      throw new Error(`Desktop font projection is stale: ${target.pathname}`);
  } else {
    mkdirSync(new URL(".", target), { recursive: true });
    writeFileSync(target, expected);
  }
}
