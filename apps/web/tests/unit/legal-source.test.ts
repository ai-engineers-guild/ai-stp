import { describe, expect, it } from "vitest";

import { legalSourceUrl } from "@/lib/api/legal";

describe("legalSourceUrl", () => {
  it("links a legal Markdown source to its deployed Git commit", () => {
    const commit = "a".repeat(40);
    const path = "docs-user-facing/legal/en/privacy/1.0/document.md";
    expect(legalSourceUrl({ source_ref: commit, source_path: path })).toBe(
      `https://github.com/ai-engineers-guild/ai-stp/blob/${commit}/${path}`,
    );
    expect(legalSourceUrl({ source_ref: commit, source_path: "docs/private.md" })).toBeNull();
  });
});
