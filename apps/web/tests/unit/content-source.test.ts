import { describe, expect, it } from "vitest";

import {
  allContentEntries,
  assertContentLocaleParity,
  CONTENT_TYPES,
  publishedContent,
} from "@/lib/content/source";

describe("git-native content source", () => {
  it("publishes every content type in both locales", () => {
    assertContentLocaleParity();
    for (const locale of ["en", "ru"]) {
      expect(new Set(publishedContent(locale).map((entry) => entry.type))).toEqual(
        new Set(CONTENT_TYPES),
      );
    }
  });

  it("keeps drafts out of public reads and identities unique", () => {
    const entries = allContentEntries();
    expect(publishedContent("en").every((entry) => !entry.draft)).toBe(true);
    expect(
      new Set(entries.map((entry) => `${entry.locale}:${entry.type}:${entry.slug}`)).size,
    ).toBe(entries.length);
  });
});
