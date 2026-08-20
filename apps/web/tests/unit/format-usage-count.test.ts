import { describe, expect, it } from "vitest";

import { formatUsageCount } from "@/lib/format-usage-count";

describe("formatUsageCount", () => {
  it("keeps small integers exact and compactifies large totals", () => {
    expect(formatUsageCount(0, "en")).toBe("0");
    expect(formatUsageCount(12, "en")).toBe("12");
    expect(formatUsageCount(12_400, "en")).toMatch(/12/u);
    expect(formatUsageCount(12_400, "ru")).toMatch(/12/u);
  });
});
