import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { IntlMessageFormat } from "intl-messageformat";
import ts from "typescript";
import { parameters, selectors } from "./message-parameters.mjs";

const directory = new URL("../src/locales/", import.meta.url);
const configuration = JSON.parse(
  readFileSync(new URL("../src/localization.json", import.meta.url), "utf8"),
);
const catalogs = Object.keys(configuration.languages).map(
  (locale) => `${locale}.json`,
);
const source = JSON.parse(
  readFileSync(
    new URL(`${configuration.defaultLocale}.json`, directory),
    "utf8",
  ),
);
const sourceDirectory = fileURLToPath(new URL("../src/", import.meta.url));
const keys = new Set(Object.keys(source));
const used = new Set();
const untranslated = [];
const attributes = new Set([
  "title",
  "description",
  "eyebrow",
  "aria-label",
  "placeholder",
  "alt",
  "label",
]);
const human = (text) => /\p{L}/u.test(text) && text.trim() !== "ai-stp";

function display(node) {
  for (let parent = node.parent; parent; parent = parent.parent) {
    if (ts.isCallExpression(parent)) {
      if (
        ts.isIdentifier(parent.expression) &&
        ["String", "Number"].includes(parent.expression.text)
      )
        continue;
      return false;
    }
    if (
      ts.isPropertyAccessExpression(parent) ||
      ts.isElementAccessExpression(parent)
    )
      return false;
    if (
      ts.isConditionalExpression(parent) &&
      parent.condition.pos <= node.pos &&
      node.end <= parent.condition.end
    )
      return false;
    if (ts.isBinaryExpression(parent)) {
      if (
        ![
          ts.SyntaxKind.QuestionQuestionToken,
          ts.SyntaxKind.BarBarToken,
          ts.SyntaxKind.AmpersandAmpersandToken,
        ].includes(parent.operatorToken.kind)
      )
        return false;
      if (parent.left.pos <= node.pos && node.end <= parent.left.end)
        return false;
    }
    if (ts.isJsxExpression(parent))
      return ts.isJsxAttribute(parent.parent)
        ? attributes.has(parent.parent.name.getText())
        : ts.isJsxElement(parent.parent) || ts.isJsxFragment(parent.parent);
    if (ts.isJsxAttribute(parent)) return attributes.has(parent.name.getText());
    if (ts.isFunctionLike(parent) || ts.isStatement(parent)) return false;
  }
  return false;
}

function inspect(file) {
  const raw = readFileSync(file, "utf8");
  const parsed = ts.createSourceFile(
    file,
    raw,
    ts.ScriptTarget.Latest,
    true,
    file.endsWith("tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  if (parsed.parseDiagnostics.length)
    throw new Error(
      `Cannot inspect ${path.relative(sourceDirectory, file)}: invalid source`,
    );
  function visit(node) {
    if (ts.isStringLiteral(node) && keys.has(node.text)) used.add(node.text);
    let technical = false;
    for (let parent = node.parent; parent; parent = parent.parent) {
      if (
        ts.isJsxElement(parent) &&
        ["code", "pre"].includes(parent.openingElement.tagName.getText())
      ) {
        technical = true;
        break;
      }
    }
    let text = "";
    if (ts.isJsxText(node)) text = node.text.trim();
    else if (
      (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) &&
      display(node)
    )
      text = node.text;
    else if (ts.isTemplateExpression(node) && display(node))
      text =
        node.head.text +
        node.templateSpans.map((span) => span.literal.text).join("");
    if (!technical && human(text))
      untranslated.push(
        `${path.relative(sourceDirectory, file)}:${parsed.getLineAndCharacterOfPosition(node.getStart(parsed)).line + 1}: ${text.replace(/\s+/g, " ")}`,
      );
    ts.forEachChild(node, visit);
  }
  visit(parsed);
}
function walk(folder) {
  for (const entry of readdirSync(folder, { withFileTypes: true })) {
    if (entry.name === "generated") continue;
    const file = path.join(folder, entry.name);
    if (entry.isDirectory()) walk(file);
    else if (
      /\.tsx?$/.test(file) &&
      !file.includes(".test.") &&
      entry.name !== "test-setup.ts"
    )
      inspect(file);
  }
}
walk(sourceDirectory);
const unused = [...keys].filter((key) => !used.has(key));
if (unused.length) console.log(`Unused Desktop messages: ${unused.join(", ")}`);
if (untranslated.length)
  throw new Error(
    `Desktop text bypasses its catalog:\n${untranslated.join("\n")}`,
  );
if (
  JSON.stringify(
    readdirSync(directory)
      .filter((name) => name.endsWith(".json"))
      .sort(),
  ) !== JSON.stringify([...catalogs].sort())
)
  throw new Error("Packaged Desktop catalogs differ from configured languages");
const signature = (nodes) =>
  JSON.stringify([...parameters(nodes)].sort(([a], [b]) => a.localeCompare(b)));
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
      undefined,
      { ignoreTag: true },
    ).getAst();
    const original = new IntlMessageFormat(
      source[key],
      configuration.defaultLocale,
      undefined,
      { ignoreTag: true },
    ).getAst();
    if (signature(ast) !== signature(original))
      throw new Error(`${name}: argument names or kinds differ for ${key}`);
    if (selectors(ast) !== selectors(original))
      throw new Error(`${name}: selector tokens differ for ${key}`);
  }
}
console.log(
  `Checked ${catalogs.length} bundled message catalogs (${Object.keys(source).length} keys each).`,
);
