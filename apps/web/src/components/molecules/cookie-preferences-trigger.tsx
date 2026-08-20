"use client";

import { Button } from "@/components/atoms/button";

export const OPEN_COOKIE_PREFERENCES_EVENT = "ai-stp-open-cookie-preferences";

export function CookiePreferencesTrigger({ label }: { label: string }) {
  return (
    <Button
      type="button"
      variant="outline"
      onClick={() => window.dispatchEvent(new Event(OPEN_COOKIE_PREFERENCES_EVENT))}
    >
      {label}
    </Button>
  );
}
