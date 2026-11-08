import { readFileSync, writeFileSync, mkdirSync } from "node:fs";

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
if (process.argv.includes("--check")) {
  if (readFileSync(target, "utf8") !== expected)
    throw new Error(
      "Desktop bootstrap messages are stale; run just desktop-gen",
    );
} else {
  mkdirSync(new URL("../src/generated/", import.meta.url), { recursive: true });
  writeFileSync(target, expected);
}
