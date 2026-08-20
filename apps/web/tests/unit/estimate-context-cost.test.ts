import { describe, expect, it } from "vitest";

import { estimateContextCost } from "@/lib/estimate-context-cost";

describe("client-only context cost estimate", () => {
  it("applies total * rate / 1_000_000", () => {
    expect(estimateContextCost(2000, "3")).toEqual({
      status: "available",
      amount: "0.00600000",
    });
  });

  it("treats blank input as empty and rejects invalid rates", () => {
    expect(estimateContextCost(10, "  ")).toEqual({ status: "empty", amount: null });
    expect(estimateContextCost(10, "-1")).toEqual({ status: "invalid", amount: null });
    expect(estimateContextCost(10, "1e2")).toEqual({ status: "invalid", amount: null });
  });
});
