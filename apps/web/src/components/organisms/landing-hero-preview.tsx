"use client";

import { useLocale } from "next-intl";
import { useEffect, useRef } from "react";

import { landingHeroPreview } from "@/lib/landing-hero";
import { UI } from "@/lib/ui-selectors";

/**
 * Background Claude Code preview. `<source>` updates do not reload an existing
 * media element, so locale switches remount the video and call `load()`.
 */
export function LandingHeroPreview() {
  const locale = useLocale();
  const hero = landingHeroPreview(locale);
  const videoRef = useRef<HTMLVideoElement>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies(hero.webm): Changing a localized media source must reload the video element.
  // biome-ignore lint/correctness/useExhaustiveDependencies(hero.mp4): Changing a localized media source must reload the video element.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    try {
      video.load();
    } catch {
      // jsdom does not implement HTMLMediaElement.load.
    }
    try {
      void Promise.resolve(video.play()).catch(() => undefined);
    } catch {
      // jsdom may throw when media playback is not implemented.
    }
  }, [hero.webm, hero.mp4]);

  return (
    <>
      <video
        key={hero.webm}
        ref={videoRef}
        data-ui={UI.landing.preview}
        className="landing-hero__video h-full w-full object-cover motion-reduce:hidden"
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        poster={hero.poster}
        tabIndex={-1}
        aria-hidden="true"
      >
        <source src={hero.webm} type="video/webm" />
        <source src={hero.mp4} type="video/mp4" />
      </video>
      {/* biome-ignore lint/performance/noImgElement: The local video poster is also the reduced-motion fallback and keeps the same source. */}
      <img
        src={hero.poster}
        alt=""
        className="hidden h-full w-full object-cover motion-reduce:block"
      />
    </>
  );
}
