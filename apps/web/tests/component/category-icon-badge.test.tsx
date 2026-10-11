import { expect, it } from "vitest";
import { categoryIconValue, categoryLucideName } from "@/components/molecules/category-icon-badge";
import { CATEGORY_ICON_NAMES } from "@/theme/category-icons";
it("persists every selectable category glyph in the backend contract format and reads it back", () => {
  for (const name of CATEGORY_ICON_NAMES) {
    const value = categoryIconValue(name);
    expect(value).toMatch(/^lucide:[a-z0-9][a-z0-9-]{0,63}$/);
    expect(categoryLucideName(value)).toBe(name);
  }
  expect(categoryIconValue("trendingUp")).toBe("lucide:trending-up");
  expect(categoryLucideName("lucide:trendingUp")).toBe("trendingUp");
  expect(categoryLucideName("lucide:unknown-icon")).toBeNull();
});
