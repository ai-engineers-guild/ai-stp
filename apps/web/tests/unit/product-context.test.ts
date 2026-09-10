import { describe, expect, it } from "vitest";

import {
  LOCAL_CONTEXT,
  contextCacheKey,
  contextStatus,
  hasCapability,
} from "@/lib/product-context";
import {
  CONTEXT_SURFACE_MATRIX,
  CONTEXT_SURFACES,
  PRODUCT_CONTEXT_MODES,
} from "@/lib/context-surfaces";

describe("product context", () => {
  it("keeps capability checks and cache identity context-bound", () => {
    expect(hasCapability(LOCAL_CONTEXT, "project.read")).toBe(true);
    expect(hasCapability(LOCAL_CONTEXT, "organization.manage")).toBe(false);
    expect(contextCacheKey(LOCAL_CONTEXT)).toBe("local:local:1");
  });

  it("distinguishes empty remote context from local context", () => {
    expect(
      contextStatus({
        context: { ...LOCAL_CONTEXT, mode: "corporate" },
        organizations: [],
        status: "ready",
      }),
    ).toBe("empty");
    expect(contextStatus({ context: LOCAL_CONTEXT, organizations: [], status: "ready" })).toBe(
      "ready",
    );
  });

  it("keeps one closed surface matrix for every product mode", () => {
    expect(Object.keys(CONTEXT_SURFACE_MATRIX)).toEqual([...PRODUCT_CONTEXT_MODES]);
    for (const mode of PRODUCT_CONTEXT_MODES) {
      expect(Object.keys(CONTEXT_SURFACE_MATRIX[mode])).toEqual(
        CONTEXT_SURFACES.map((surface) => surface.key),
      );
    }
  });

  it("isolates stale in-flight data by authorization revision", () => {
    const first = { ...LOCAL_CONTEXT, capabilities: { ...LOCAL_CONTEXT.capabilities } };
    const second = {
      ...first,
      capabilities: { ...first.capabilities, authorization_revision: "local:2" },
    };
    expect(contextCacheKey(first)).not.toBe(contextCacheKey(second));
  });
});
