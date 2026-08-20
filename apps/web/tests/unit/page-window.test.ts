import { describe, expect, it } from "vitest";

import { pageWindow } from "@/lib/page-window";

describe("pageWindow", () => {
  it("lists every page when the set is short", () => {
    expect(pageWindow(2, 5)).toEqual([1, 2, 3, 4, 5]);
  });

  it("keeps edges and a neighbourhood around the current page", () => {
    expect(pageWindow(1, 20)).toEqual([1, 2, 3, "gap", 20]);
    expect(pageWindow(10, 20)).toEqual([1, "gap", 8, 9, 10, 11, 12, "gap", 20]);
    expect(pageWindow(20, 20)).toEqual([1, "gap", 18, 19, 20]);
  });
});
