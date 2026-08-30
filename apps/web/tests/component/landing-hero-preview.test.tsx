import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import { LandingHeroPreview } from "@/components/molecules/landing-hero-preview";

function renderPreview(locale: "en" | "ru") {
  return render(
    <NextIntlClientProvider locale={locale} messages={{}}>
      <LandingHeroPreview />
    </NextIntlClientProvider>,
  );
}

function sourceSrcs(container: HTMLElement): string[] {
  return [...container.querySelectorAll("source")].map((node) => node.getAttribute("src") ?? "");
}

describe("LandingHeroPreview", () => {
  it("plays the English reel on the English locale and swaps to Russian on rerender", () => {
    const view = renderPreview("en");
    expect(sourceSrcs(view.container)).toEqual([
      "/brand/hero-preview-en.webm",
      "/brand/hero-preview-en.mp4",
    ]);
    expect(view.container.querySelector("video")?.getAttribute("poster")).toBe(
      "/brand/hero-preview-en-poster.png",
    );

    view.rerender(
      <NextIntlClientProvider locale="ru" messages={{}}>
        <LandingHeroPreview />
      </NextIntlClientProvider>,
    );
    expect(sourceSrcs(view.container)).toEqual([
      "/brand/hero-preview.webm",
      "/brand/hero-preview.mp4",
    ]);
    expect(view.container.querySelector("video")?.getAttribute("poster")).toBe(
      "/brand/hero-preview-poster.png",
    );
  });
});
