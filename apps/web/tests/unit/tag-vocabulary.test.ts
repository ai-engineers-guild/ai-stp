import { describe, expect, it } from "vitest";

import { HARNESS_FACETS } from "@/lib/tag-vocabulary";

describe("catalog harness facets", () => {
  it("offers the complete seven-harness OBT line", () => {
    expect(HARNESS_FACETS).toEqual([
      "claude-code",
      "codex",
      "pi",
      "opencode",
      "grok-build",
      "cursor",
      "antigravity",
    ]);
  });
});
