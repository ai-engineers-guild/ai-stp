import { describe, expect, it } from "vitest";

import { UI, uiSelector } from "@/lib/ui-selectors";

function values(value: object): string[] {
  return Object.values(value).flatMap((item) =>
    typeof item === "string" ? [item] : values(item as object),
  );
}

describe("stable UI selector catalog", () => {
  it("contains unique readable selector values", () => {
    const selectors = values(UI);
    expect(new Set(selectors).size).toBe(selectors.length);
    expect(selectors.every((selector) => /^[a-z][a-z0-9-]+$/.test(selector))).toBe(true);
  });

  it("builds an attribute selector without coupling tests to classes", () => {
    expect(uiSelector(UI.projection.toggle)).toBe('[data-ui="human-machine-toggle"]');
    expect(uiSelector(UI.theme.toggle)).toBe('[data-ui="color-theme-toggle"]');
  });
});
