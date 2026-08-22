"use client";

import { useSessionPresence } from "@/lib/auth/use-session-presence";

/**
 * Render children only while this browser has no session.
 *
 * The landing is static, so its HTML is the same for everybody and always
 * contains the signed-out version. A visitor who turns out to be signed in
 * loses this after hydration; a visitor who is not keeps it and never saw
 * anything move.
 *
 * That order matters: showing "Sign in" to a signed-in visitor for a moment is
 * a cosmetic slip, while hiding it until a fetch answers would blank a control
 * that most visitors — anonymous ones — came for.
 */
export function SignedOutOnly({ children }: { children: React.ReactNode }) {
  return useSessionPresence() ? null : <>{children}</>;
}
