import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { IntlMessageFormat } from "intl-messageformat";
import { format } from "prettier";
import { parameters } from "./message-parameters.mjs";

const configuration = JSON.parse(
  readFileSync(new URL("../src/localization.json", import.meta.url), "utf8"),
);
const source = JSON.parse(
  readFileSync(
    new URL(
      `../src/locales/${configuration.defaultLocale}.json`,
      import.meta.url,
    ),
    "utf8",
  ),
);
const bootstrap = Object.fromEntries(
  Object.entries(source).filter(([key]) =>
    configuration.bootstrapPrefixes.some((prefix) => key.startsWith(prefix)),
  ),
);
const target = new URL(
  "../src/generated/messages-bootstrap.json",
  import.meta.url,
);
const expected = JSON.stringify(bootstrap, null, 2) + "\n";
const fields = [];
for (const [key, value] of Object.entries(source)) {
  const args = parameters(
    new IntlMessageFormat(value, configuration.defaultLocale, undefined, {
      ignoreTag: true,
    }).getAst(),
  );
  if (args.size)
    fields.push(
      `${JSON.stringify(key)}: { ${[...args].map(([name, type]) => `${JSON.stringify(name)}: ${type};`).join(" ")} };`,
    );
}
const types = await format(
  `// Generated from the English ICU catalog; do not edit.\nexport type MessageValues = {\n${fields.join("\n")}\n};\n`,
  { parser: "typescript" },
);
const typesTarget = new URL(
  "../src/generated/message-values.ts",
  import.meta.url,
);
if (process.argv.includes("--check")) {
  if (readFileSync(target, "utf8") !== expected)
    throw new Error(
      "Desktop bootstrap messages are stale; run just desktop-gen",
    );
  if (readFileSync(typesTarget, "utf8") !== types)
    throw new Error(
      "Desktop message parameter types are stale; run just desktop-gen",
    );
} else {
  mkdirSync(new URL("../src/generated/", import.meta.url), { recursive: true });
  writeFileSync(target, expected);
  writeFileSync(typesTarget, types);
}
