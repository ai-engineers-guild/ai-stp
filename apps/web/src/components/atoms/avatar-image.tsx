"use client";

import Image from "next/image";
import { useState, type ReactNode } from "react";

import { cn } from "@/lib/cn";

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

/** Two-letter initials circle — the shared fallback for person identity. */
export function InitialsAvatar({ name, className }: { name: string; className?: string }) {
  const initials = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  return (
    <span
      aria-hidden
      className={cn(
        "bg-muted text-foreground grid size-8 shrink-0 place-items-center rounded-full text-xs font-medium",
        className,
      )}
    >
      {initials}
    </span>
  );
}
