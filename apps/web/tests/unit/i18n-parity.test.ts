import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import en from "../../messages/en.json";
import ru from "../../messages/ru.json";
import { CORPORATE_NAV_PAGES } from "../../src/lib/corporate-navigation-pages";

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

// `withFileTypes` answers the kind from the same directory read, so there is
// no second lookup of the path between deciding what it is and opening it. The
// previous `statSync` then `readFileSync` was two lookups of one name — a
// window CodeQL reports as a file-system race, and a test that walks a source
// tree has no reason to leave one open.
function walkSource(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "stories" || entry.name === "generated") return [];
      return walkSource(full);
    }
    if (!/\.(ts|tsx)$/.test(entry.name)) return [];
    return [readFileSync(full, "utf8")];
  });
}

function walkFiles(dir: string): Array<{ file: string; text: string }> {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "stories" || entry.name === "generated") return [];
      return walkFiles(full);
    }
    if (!/\.(ts|tsx)$/.test(entry.name)) return [];
    return [{ file: full, text: readFileSync(full, "utf8") }];
  });
}

const TRANSLATOR_BINDING =
  /\b(\w+)\s*=\s*(?:await\s+)?(?:useTranslations|getTranslations)\(\s*["']([\w.]*)["']\s*\)/g;

function usedKeys(file: string, text: string, known: Set<string>): string[] {
  const namespaces = new Map<string, Set<string>>();
  for (const match of text.matchAll(TRANSLATOR_BINDING)) {
    const [, identifier, namespace] = match;
    if (identifier === undefined || namespace === undefined) continue;
    const bucket = namespaces.get(identifier) ?? new Set<string>();
    bucket.add(namespace);
    namespaces.set(identifier, bucket);
  }
  const missing: string[] = [];
  for (const [identifier, bucket] of namespaces) {
    // A helper may receive the translator as a parameter (t: (key) => string);
    // its namespace is unknowable statically, so only require that the key
    // exists somewhere in the catalog rather than under a bound namespace.
    const param = new RegExp(`[({,]\\s*${identifier}\\s*[,:)}]`).test(text);
    const calls = new RegExp(`\\b${identifier}\\(\\s*["']([\\w.]+)["']`, "g");
    for (const match of text.matchAll(calls)) {
      const leaf = match[1];
      if (leaf === undefined) continue;
      const resolved = param
        ? [...known].some((key) => key === leaf || key.endsWith(`.${leaf}`))
        : [...bucket].some((ns) => known.has(ns ? `${ns}.${leaf}` : leaf));
      if (!resolved) missing.push(`${file}: ${identifier}("${leaf}")`);
    }
  }
  return missing;
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

  it("every literal key used through a bound translator exists", () => {
    const known = new Set(enKeys);
    const missing = walkFiles(SRC_ROOT).flatMap(({ file, text }) => usedKeys(file, text, known));
    expect(missing).toEqual([]);
  });

  it("every access-model section has a description in both locales", () => {
    for (const catalog of [en, ru]) {
      const sections: Record<string, string> = catalog.accessUi.sections;
      for (const page of CORPORATE_NAV_PAGES.filter((item) => item.rail || item.root)) {
        expect(sections[page.id], page.id).toEqual(expect.any(String));
        expect(sections[page.id]?.trim(), page.id).not.toBe("");
      }
    }
  });

  it("every corporate rail label resolves in the hub namespace", () => {
    const hubKeys = new Set(
      enKeys.filter((key) => key.startsWith("hub.")).map((key) => key.slice(4)),
    );
    const labels = CORPORATE_NAV_PAGES.flatMap((page) =>
      [page.label, page.rootLabel, page.group].filter(
        (label): label is string => typeof label === "string",
      ),
    );
    const missing = labels.filter((label) => !hubKeys.has(label));
    expect(missing).toEqual([]);
  });
});
