import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { loadContextBudget } from "@/lib/context-budget";

describe("loadContextBudget", () => {
  it("retains a successful exact response", async () => {
    const budget = { status: "ready", total_tokens: 40 };
    expect(await loadContextBudget(Promise.resolve(budget))).toEqual({ budget, failure: null });
  });

  it.each([
    ["AI_STP_VALIDATION_ERROR", "invalid_graph"],
    ["AI_STP_NOT_FOUND", "artifact_unavailable"],
    ["AI_STP_UNAVAILABLE", "dependency_unavailable"],
  ] as const)("preserves the reason for %s", async (code, failure) => {
    const error = new ApiError({ code, message: "Unavailable", status: 503 });
    expect(await loadContextBudget(Promise.reject(error))).toEqual({ budget: null, failure });
  });
});
