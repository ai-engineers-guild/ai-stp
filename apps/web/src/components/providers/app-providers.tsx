"use client";

import { ThemeProvider } from "next-themes";
import { usePathname, useSearchParams } from "next/navigation";
import { Toaster } from "sonner";
import { useEffect, useRef } from "react";

import {
  currentNavigationHref,
  getNavigationStorage,
  recordNavigation,
  updateCurrentNavigation,
} from "@/lib/navigation-history";

type AppProvidersProps = {
  children: React.ReactNode;
};

export function AppProviders({ children }: AppProvidersProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const search = searchParams.toString();
  const popState = useRef(false);

  useEffect(() => {
    const onPopState = () => {
      popState.current = true;
    };
    window.addEventListener("popstate", onPopState);

    const originalReplaceState = window.history.replaceState.bind(window.history);
    window.history.replaceState = ((state: unknown, unused: string, url?: string | URL | null) => {
      originalReplaceState.call(window.history, state, unused, url);
      const storage = getNavigationStorage();
      if (storage) updateCurrentNavigation(storage, currentNavigationHref(window.location));
    }) as History["replaceState"];

    return () => {
      window.removeEventListener("popstate", onPopState);
      window.history.replaceState = originalReplaceState;
    };
  }, []);

  useEffect(() => {
    const storage = getNavigationStorage();
    if (!storage) return;
    const restoreScroll = recordNavigation(
      storage,
      currentNavigationHref(window.location),
      popState.current,
      window.scrollY,
    );
    popState.current = false;
    if (restoreScroll === null) return;
    window.requestAnimationFrame(() => {
      window.scrollTo({ top: restoreScroll, left: 0, behavior: "auto" });
    });
  }, [pathname, search]);

  useEffect(() => {
    let timeout: number | undefined;
    const onScroll = () => {
      window.clearTimeout(timeout);
      timeout = window.setTimeout(() => {
        const storage = getNavigationStorage();
        if (storage)
          updateCurrentNavigation(storage, currentNavigationHref(window.location), window.scrollY);
      }, 100);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.clearTimeout(timeout);
    };
  }, []);

  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="light"
      enableSystem={false}
      storageKey="ai_stp_color_theme"
      disableTransitionOnChange
    >
      {children}
      <Toaster richColors position="top-center" closeButton />
    </ThemeProvider>
  );
}
