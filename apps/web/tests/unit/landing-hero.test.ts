import { describe, expect, it } from "vitest";

import { landingHeroPreview } from "@/lib/landing-hero";

describe("landingHeroPreview", () => {
  it("uses the English Claude Code reel for en", () => {
    expect(landingHeroPreview("en")).toEqual({
      webm: "/brand/hero-preview-en.webm",
      mp4: "/brand/hero-preview-en.mp4",
      poster: "/brand/hero-preview-en-poster.png",
    });
  });

  it("uses the Russian Claude Code reel for ru and any other locale", () => {
    expect(landingHeroPreview("ru").webm).toBe("/brand/hero-preview.webm");
    expect(landingHeroPreview("ru").mp4).toBe("/brand/hero-preview.mp4");
    expect(landingHeroPreview("").webm).toBe("/brand/hero-preview.webm");
  });
});
