import { readFileSync, readdirSync } from "node:fs";
import { IntlMessageFormat } from "intl-messageformat";

const directory = new URL("../src/locales/", import.meta.url);
const catalogs = readdirSync(directory).filter((name) =>
  name.endsWith(".json"),
);
const source = JSON.parse(readFileSync(new URL("en.json", directory), "utf8"));
function variables(nodes, output = new Set()) {
  for (const node of nodes) {
    if (node.type !== 0 && node.value) output.add(node.value);
    if (node.children) variables(node.children, output);
    if (node.options)
      for (const option of Object.values(node.options))
        variables(option.value, output);
  }
  return [...output].sort().join(",");
}
for (const name of catalogs) {
  const messages = JSON.parse(readFileSync(new URL(name, directory), "utf8"));
  if (
    JSON.stringify(Object.keys(messages).sort()) !==
    JSON.stringify(Object.keys(source).sort())
  ) {
    throw new Error(`${name}: message keys differ from English`);
  }
  for (const [key, value] of Object.entries(messages)) {
    if (typeof value !== "string" || !value.trim())
      throw new Error(`${name}: empty message ${key}`);
    const ast = new IntlMessageFormat(
      value,
      name.replace(".json", ""),
    ).getAst();
    const original = new IntlMessageFormat(source[key], "en").getAst();
    if (variables(ast) !== variables(original))
      throw new Error(`${name}: variables differ for ${key}`);
  }
}
console.log(
  `Checked ${catalogs.length} bundled message catalogs (${Object.keys(source).length} keys each).`,
);
