import { describe, expect, it } from "vitest";

import {
  ENTITY_EDITOR_CONFIGS,
  validateEntityDisplayName,
  validateEntityLinks,
} from "@/lib/entity-editor-contract";

describe("entity editor contract", () => {
  it("gives every editable entity the shared base blocks", () => {
    for (const config of Object.values(ENTITY_EDITOR_CONFIGS)) {
      expect(config.blocks).toEqual(
        expect.arrayContaining(["displayName", "description", "links"]),
      );
      expect(config.limits.links).toBe(5);
    }
  });

  it("validates required display names and bounded links", () => {
    expect(validateEntityDisplayName("   ")).toContain("required");
    expect(validateEntityDisplayName("Project")).toBeNull();
    expect(validateEntityLinks([{ label: "Docs", url: "http://example.com" }])).toBe(
      "Links must use HTTPS",
    );
    expect(
      validateEntityLinks([
        { label: "Docs", url: "https://example.com" },
        { label: "Docs again", url: "https://example.com" },
      ]),
    ).toBe("Links must be unique");
  });
});
