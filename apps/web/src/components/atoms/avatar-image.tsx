"use client";

import Image from "next/image";
import { useState, type ReactNode } from "react";

type AvatarImageProps = {
  src: string | null | undefined;
  className: string;
  fallback: ReactNode;
  width?: number;
  height?: number;
};

/** Keeps broken or stale avatar URLs from leaking the browser's broken-image UI. */
export function AvatarImage({ src, className, fallback, width, height }: AvatarImageProps) {
  // Which URL failed, not whether one did. A boolean needed an effect to clear
  // it when `src` changed, and that effect ran on every avatar that never
  // failed at all; comparing the recorded URL answers the same question during
  // render and resets itself.
  const [failedSrc, setFailedSrc] = useState<string | null>(null);

  if (!src || failedSrc === src) return fallback;
  const renderedWidth = width ?? 36;
  const renderedHeight = height ?? renderedWidth;
  return (
    <Image
      src={src}
      alt=""
      width={renderedWidth}
      height={renderedHeight}
      sizes={`${renderedWidth}px`}
      className={className}
      onError={() => {
        setFailedSrc(src);
      }}
    />
  );
}
