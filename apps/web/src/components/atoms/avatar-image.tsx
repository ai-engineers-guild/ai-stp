"use client";

import { useEffect, useState, type ReactNode } from "react";

type AvatarImageProps = {
  src: string | null | undefined;
  className: string;
  fallback: ReactNode;
  width?: number;
  height?: number;
};

/** Keeps broken or stale avatar URLs from leaking the browser's broken-image UI. */
export function AvatarImage({ src, className, fallback, width, height }: AvatarImageProps) {
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [src]);

  if (!src || failed) return fallback;
  return (
    <img
      src={src}
      alt=""
      width={width}
      height={height}
      className={className}
      onError={() => {
        setFailed(true);
      }}
    />
  );
}
