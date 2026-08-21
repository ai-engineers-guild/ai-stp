import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import en from "../../messages/en.json";
import ru from "../../messages/ru.json";

const SRC_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../src");

function flatten(value: unknown, prefix = ""): Array<{ key: string; text: string }> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    if (typeof value !== "string") {
      return prefix ? [{ key: prefix, text: "" }] : [];
    }
    return prefix ? [{ key: prefix, text: value }] : [];
  }
  return Object.entries(value as Record<string, unknown>).flatMap(([child, nested]) =>
    flatten(nested, prefix ? `${prefix}.${child}` : child),
  );
}

function walkSource(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name === "stories" || name === "generated") return [];
      return walkSource(full);
    }
    if (!/\.(ts|tsx)$/.test(name)) return [];
    return [readFileSync(full, "utf8")];
  });
}

describe("i18n parity (REQ-2203, REQ-2311)", () => {
  const enEntries = flatten(en);
  const ruEntries = flatten(ru);
  const enKeys = enEntries.map((item) => item.key).sort();
  const ruKeys = ruEntries.map((item) => item.key).sort();
  const source = walkSource(SRC_ROOT).join("\n");

  it("ru and en catalogs expose the same keys", () => {
    expect(ruKeys).toEqual(enKeys);
  });

  it("catalog values are non-empty in both locales", () => {
    const empty = [...enEntries, ...ruEntries]
      .filter((item) => item.text.trim() === "")
      .map((item) => item.key);
    expect(empty).toEqual([]);
  });

  it("every catalog key is referenced from application source", () => {
    const missing = enKeys.filter((key) => {
      const leaf = key.split(".").at(-1) ?? key;
      return !source.includes(`"${leaf}"`) && !source.includes(`'${leaf}'`);
    });
    expect(missing).toEqual([]);
  });
});
