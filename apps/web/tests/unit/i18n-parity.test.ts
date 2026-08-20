import { describe, expect, it } from "vitest";

import en from "../../messages/en.json";
import ru from "../../messages/ru.json";

function flattenKeys(value: unknown, prefix = ""): string[] {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return prefix ? [prefix] : [];
  }
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    flattenKeys(child, prefix ? `${prefix}.${key}` : key),
  );
}

describe("i18n parity (REQ-2203, REQ-2311)", () => {
  it("ru and en catalogs expose the same keys", () => {
    const enKeys = flattenKeys(en).sort();
    const ruKeys = flattenKeys(ru).sort();
    expect(ruKeys).toEqual(enKeys);
  });
});
