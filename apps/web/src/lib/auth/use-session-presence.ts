"use client";

import { useEffect } from "react";

import { usePathname } from "@/lib/i18n/navigation";
import { useSessionUiSlice } from "@/lib/stores/session-ui-slice";

/**
 * Learn, after hydration, whether this browser has a session.
 *
 * The shell is rendered statically and is the same bytes for everybody, so the
 * server cannot tell the header which controls to show. `/api/session` can:
 * it is a request-time route handler, and it answers presence and nothing else.
 *
 * Asked again on every route change, and that is not incidental. The header
 * lives in the layout, so it survives client-side navigation without
 * remounting — and signing in *is* a client-side navigation, from `/login` to
 * `/account`. Asking only on mount would answer "signed out" once, before the
 * cookie exists, and keep that answer for the rest of the visit.
 *
 * Deliberately fire-and-forget. A visitor who is signed out is the common case
 * and already sees the right header; one who is signed in sees it a moment
 * later. Neither outcome should be able to fail a page render, so a network
 * error leaves the hint alone rather than asserting signed-out — flipping a
 * correct hint to false on a flaky request would log the header out visually
 * while the session is still perfectly good.
 */
export function useSessionPresence(): boolean {
  const signedInHint = useSessionUiSlice((s) => s.signedInHint);
  const setSignedInHint = useSessionUiSlice((s) => s.setSignedInHint);
  const pathname = usePathname();

  useEffect(() => {
    const aborter = new AbortController();
    void (async () => {
      try {
        const response = await fetch("/api/session", {
          cache: "no-store",
          credentials: "same-origin",
          signal: aborter.signal,
        });
        if (!response.ok) {
          return;
        }
        const body = (await response.json()) as { signedIn?: unknown };
        if (typeof body.signedIn === "boolean") {
          setSignedInHint(body.signedIn);
        }
      } catch {
        // Left as it was; see the note above.
      }
    })();
    return () => {
      aborter.abort();
    };
  }, [setSignedInHint, pathname]);

  return signedInHint;
}
