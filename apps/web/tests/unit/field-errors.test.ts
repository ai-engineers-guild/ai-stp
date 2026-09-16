import { describe, expect, it } from "vitest";

import { fieldErrorsFromDetails, normalizeFieldPath } from "@/lib/api/field-errors";

describe("API field errors", () => {
  it("normalizes Pydantic body and fields prefixes", () => {
    expect(normalizeFieldPath("body.fields.links[1].url")).toBe("links.1.url");
    expect(normalizeFieldPath("body.media.0.alt")).toBe("media.0.alt");
  });

  it("reads string, object, and loc-based backend field errors", () => {
    expect(
      fieldErrorsFromDetails(
        {
          fields: [
            "body.fields.links.0.url",
            { path: "body.fields.media.0.alt", message: "alt required" },
            { loc: ["body", "fields", "media", 1, "url"], detail: "source invalid" },
          ],
        },
        "request validation failed",
      ),
    ).toEqual({
      "links.0.url": "request validation failed",
      "media.0.alt": "alt required",
      "media.1.url": "source invalid",
    });
  });
});
