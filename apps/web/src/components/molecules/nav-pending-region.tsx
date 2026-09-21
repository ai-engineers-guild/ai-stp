"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { useSearchParams } from "next/navigation";

import { cn } from "@/lib/cn";
import { usePathname } from "@/lib/i18n/navigation";

/**
 * Shows a slim progress bar while a navigation triggered by a link inside the
 * region is still rendering. App Router keeps the old page visible during soft
 * navigations, so without this the UI looks frozen. Form submits are covered
 * by the form's own transition indicator. No opacity dimming: opacity < 1 on
 * the wrapper would become a containing block for fixed-position descendants
 * (the filter drawer) and corrupt their layout.
 */
export function NavPendingRegion({
  children,
  className,
  label = "Loading",
}: {
  children: ReactNode;
  className?: string;
  label?: string;
}) {
  const [pending, setPending] = useState(false);
  const pathname = usePathname();
  // Returns null outside a Next router context (unit tests render bare regions).
  const searchParams = useSearchParams() as ReturnType<typeof useSearchParams> | null;
  const locationKey = `${pathname}?${searchParams?.toString() ?? ""}`;
  const previousKey = useRef(locationKey);

  useEffect(() => {
    if (previousKey.current !== locationKey) {
      previousKey.current = locationKey;
      setPending(false);
    }
  }, [locationKey]);

  useEffect(() => {
    if (!pending) return;
    const timeout = setTimeout(() => {
      setPending(false);
    }, 15000);
    return () => {
      clearTimeout(timeout);
    };
  }, [pending]);

  return (
    <div
      className={cn("relative min-w-0", className)}
      aria-busy={pending}
      onClickCapture={(event) => {
        const anchor = (event.target as HTMLElement).closest<HTMLAnchorElement>("a[href]");
        if (!anchor || anchor.target === "_blank" || event.defaultPrevented) return;
        const url = new URL(anchor.href, window.location.href);
        if (url.origin !== window.location.origin) return;
        if (url.pathname === window.location.pathname && url.search === window.location.search) {
          return;
        }
        setPending(true);
      }}
    >
      {pending ? (
        <div
          className="bg-muted absolute inset-x-0 top-0 z-30 h-0.5 overflow-hidden rounded-full"
          role="status"
          aria-label={label}
        >
          <div className="bg-primary h-full w-2/5 animate-pulse" />
        </div>
      ) : null}
      {children}
    </div>
  );
}
