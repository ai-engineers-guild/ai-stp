"use client";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/atoms/button";
import { OPEN_COOKIE_PREFERENCES_EVENT } from "@/components/molecules/cookie-preferences-trigger";
import { CONSENT_COOKIE, parseConsentCookie, serializeConsent, type Consent } from "@/lib/consent";

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
export function CookieConsent({ labels, privacyHref }: { labels: Labels; privacyHref: string }) {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [draft, setDraft] = useState<Consent>({ analytics: false, marketing: false });
  useEffect(() => {
    setMounted(true);
    const saved = parseConsentCookie(document.cookie);
    if (saved) setDraft(saved);
    else setOpen(true);
    const reopen = () => {
      const current = parseConsentCookie(document.cookie);
      if (current) setDraft(current);
      setOpen(true);
    };
    window.addEventListener(OPEN_COOKIE_PREFERENCES_EVENT, reopen);
    return () => {
      window.removeEventListener(OPEN_COOKIE_PREFERENCES_EVENT, reopen);
    };
  }, []);
  function persist(value: Consent) {
    document.cookie = `${CONSENT_COOKIE}=${serializeConsent(value)}; Path=/; Max-Age=15552000; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
    setDraft(value);
    setOpen(false);
    window.dispatchEvent(new CustomEvent("ai-stp-consent", { detail: value }));
  }
  if (!mounted || !open) return null;
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
              setDraft({ ...draft, analytics: event.target.checked });
            }}
          />{" "}
          {labels.analytics}
        </label>
        <label className="flex gap-2">
          <input
            type="checkbox"
            checked={draft.marketing}
            onChange={(event) => {
              setDraft({ ...draft, marketing: event.target.checked });
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
