/** Locale-specific landing hero preview assets. */
export type LandingHeroPreview = {
  webm: string;
  mp4: string;
  poster: string;
};

export function landingHeroPreview(locale: string): LandingHeroPreview {
  if (locale === "en") {
    return {
      webm: "/brand/hero-preview-en.webm",
      mp4: "/brand/hero-preview-en.mp4",
      poster: "/brand/hero-preview-en-poster.png",
    };
  }
  return {
    webm: "/brand/hero-preview.webm",
    mp4: "/brand/hero-preview.mp4",
    poster: "/brand/hero-preview-poster.png",
  };
}
