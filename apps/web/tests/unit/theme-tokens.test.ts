import { describe, expect, it } from "vitest";

import {
  COLOR_ROLES,
  TOKENS_PATH,
  colorChannels,
  fontSizes,
  iconSizes,
  radii,
  spacing,
} from "@/theme";

describe("theme tokens (Open Design portable surface)", () => {
  it("exposes every semantic color role for light and dark", () => {
    expect(COLOR_ROLES.length).toBeGreaterThanOrEqual(18);
    for (const role of COLOR_ROLES) {
      expect(colorChannels(role, "light")).toMatch(/^\d+ \d+% \d+%$/);
      expect(colorChannels(role, "dark")).toMatch(/^\d+ \d+% \d+%$/);
    }
  });

  it("keeps brand signal orange and primary hover in the token graph", () => {
    expect(COLOR_ROLES).toContain("primary");
    expect(COLOR_ROLES).toContain("primary-hover");
    // #fb631b → 19 97% 55%; #f4793f → 19 89% 60%
    expect(colorChannels("primary", "light")).toBe("19 97% 55%");
    expect(colorChannels("primary", "dark")).toBe("19 97% 55%");
    expect(colorChannels("primary-hover", "light")).toBe("19 89% 60%");
    expect(colorChannels("primary-hover", "dark")).toBe("19 89% 60%");
    expect(colorChannels("background", "dark")).toBe("0 0% 6%");
  });

  it("keeps spacing, radius, type, and icon scales non-empty", () => {
    expect(Object.keys(spacing).length).toBeGreaterThan(8);
    expect(radii.base).toBe("0.5rem");
    expect(radii.sm).toBe("0.25rem");
    expect(radii.md).toBe("0.375rem");
    expect(fontSizes.base).toBe("1rem");
    expect(iconSizes.sm).toBe("1rem");
    expect(iconSizes.md).toBe("1.25rem");
    expect(iconSizes.lg).toBe("1.5rem");
  });

  it("documents the portable tokens path for Open Design import", () => {
    expect(TOKENS_PATH).toBe("src/theme/tokens.json");
  });
});
