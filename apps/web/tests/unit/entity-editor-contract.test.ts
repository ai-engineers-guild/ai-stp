import { describe, expect, it } from "vitest";

import {
  ENTITY_EDITOR_CONFIGS,
  validateEntityFieldErrors,
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

  it("returns the exact field path for every link validation error", () => {
    expect(
      validateEntityFieldErrors(
        "Project",
        [
          { label: "", url: "https://example.com" },
          { label: "Docs", url: "http://example.com" },
        ],
        { displayName: 200, links: 5 },
        {
          displayNameRequired: "name required",
          displayNameTooLong: "name too long",
          tooManyLinks: "too many links",
          linkLabelRequired: "label required",
          linkLabelTooLong: "label too long",
          linkUrl: "url invalid",
          duplicateLink: "duplicate",
        },
      ),
    ).toEqual({
      "links.0.label": "label required",
      "links.1.url": "url invalid",
    });
  });
});
