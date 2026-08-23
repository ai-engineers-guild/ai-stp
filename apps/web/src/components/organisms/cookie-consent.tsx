"use client";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/atoms/button";
import { OPEN_COOKIE_PREFERENCES_EVENT } from "@/components/molecules/cookie-preferences-trigger";
import { CONSENT_COOKIE, parseConsentCookie, serializeConsent, type Consent } from "@/lib/consent";
import { useHydrated } from "@/lib/use-hydrated";

type Labels = {
  title: string;
  body: string;
  necessary: string;
  analytics: string;
  marketing: string;
  accept: string;
  reject: string;
  save: string;
  manage: string;
  privacy: string;
};
/** The consent cookie, read where it exists and absent where it does not. */
function subscribeToConsent(notify: () => void) {
  window.addEventListener(OPEN_COOKIE_PREFERENCES_EVENT, notify);
  window.addEventListener("ai-stp-consent", notify);
  return () => {
    window.removeEventListener(OPEN_COOKIE_PREFERENCES_EVENT, notify);
    window.removeEventListener("ai-stp-consent", notify);
  };
}

//: `useSyncExternalStore` compares snapshots by identity, so reading the cookie
//: afresh on every call would loop. The raw string is the snapshot; parsing
//: happens once per distinct value.
const readConsentCookie = () => document.cookie;
const noConsentOnTheServer = () => "";

export function CookieConsent({ labels, privacyHref }: { labels: Labels; privacyHref: string }) {
  // Read during render rather than written from an effect. The saved value
  // decides both what the form shows and whether the banner opens at all, and
  // an effect that set both produced a second render pass on every visit.
  const cookie = useSyncExternalStore(subscribeToConsent, readConsentCookie, noConsentOnTheServer);
  const saved = useMemo(() => parseConsentCookie(cookie), [cookie]);
  const mounted = useHydrated();
  // `null` means "not decided here yet": the banner opens when nothing is
  // saved, and closes only when this component closes it.
  const [dismissed, setDismissed] = useState<Consent | null>(null);
  const [edited, setEdited] = useState<Consent | null>(null);
  const draft = edited ?? saved ?? { analytics: false, marketing: false };
  const open = mounted && dismissed === null && (saved === null || edited !== null);

  useEffect(() => {
    const reopen = () => {
      setDismissed(null);
      setEdited(parseConsentCookie(document.cookie) ?? { analytics: false, marketing: false });
    };
    window.addEventListener(OPEN_COOKIE_PREFERENCES_EVENT, reopen);
    return () => {
      window.removeEventListener(OPEN_COOKIE_PREFERENCES_EVENT, reopen);
    };
  }, []);

  function persist(value: Consent) {
    document.cookie = `${CONSENT_COOKIE}=${serializeConsent(value)}; Path=/; Max-Age=15552000; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
    setEdited(null);
    setDismissed(value);
    window.dispatchEvent(new CustomEvent("ai-stp-consent", { detail: value }));
  }
  if (!open) return null;
  return createPortal(
    <section
      role="dialog"
      aria-modal="true"
      aria-labelledby="consent-title"
      className="border-border bg-background fixed bottom-4 left-1/2 z-50 w-[calc(100%-2rem)] max-w-2xl -translate-x-1/2 rounded-lg border p-4 shadow-xl sm:p-5"
    >
      <h2 id="consent-title" className="text-lg font-semibold">
        {labels.title}
      </h2>
      <p className="text-muted-foreground mt-2 text-sm">{labels.body}</p>
      <a className="mt-2 inline-block text-sm underline" href={privacyHref}>
        {labels.privacy}
      </a>
      <div className="mt-4 space-y-2">
        <label className="flex gap-2">
          <input type="checkbox" checked disabled /> {labels.necessary}
        </label>
        <label className="flex gap-2">
          <input
            type="checkbox"
            checked={draft.analytics}
            onChange={(event) => {
              setEdited({ ...draft, analytics: event.target.checked });
            }}
          />{" "}
          {labels.analytics}
        </label>
        <label className="flex gap-2">
          <input
            type="checkbox"
            checked={draft.marketing}
            onChange={(event) => {
              setEdited({ ...draft, marketing: event.target.checked });
            }}
          />{" "}
          {labels.marketing}
        </label>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <Button
          onClick={() => {
            persist({ analytics: true, marketing: true });
          }}
        >
          {labels.accept}
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            persist({ analytics: false, marketing: false });
          }}
        >
          {labels.reject}
        </Button>
        <Button
          variant="secondary"
          onClick={() => {
            persist(draft);
          }}
        >
          {labels.save}
        </Button>
      </div>
    </section>,
    document.body,
  );
}
