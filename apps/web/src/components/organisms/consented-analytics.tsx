"use client";

import { GoogleAnalytics } from "@next/third-parties/google";
import { useEffect, useMemo, useSyncExternalStore } from "react";

import { CONSENT_COOKIE, parseConsentCookie, serializeConsent, type Consent } from "@/lib/consent";
import { stopBrowserAnalytics, YANDEX_TAG_SRC } from "@/lib/public-analytics";

type ConsentedAnalyticsProps = {
  gaMeasurementId: string;
  yandexCounterId: string;
};

let consentRevision = 0;
let consentCookie = "";

function subscribeToConsent(notify: () => void) {
  consentCookie = document.cookie;
  const onConsent = (event: Event) => {
    consentRevision += 1;
    consentCookie = `${CONSENT_COOKIE}=${serializeConsent((event as CustomEvent<Consent>).detail)}`;
    notify();
  };
  window.addEventListener("ai-stp-consent", onConsent);
  return () => {
    window.removeEventListener("ai-stp-consent", onConsent);
    consentCookie = "";
  };
}

const readConsentCookie = () => `${consentRevision}\n${consentCookie || document.cookie}`;
const noConsentOnTheServer = () => "";

export function ConsentedAnalytics({ gaMeasurementId, yandexCounterId }: ConsentedAnalyticsProps) {
  const cookie = useSyncExternalStore(subscribeToConsent, readConsentCookie, noConsentOnTheServer);
  const consent = useMemo<Consent | null>(
    () => parseConsentCookie(cookie.split("\n", 2)[1] ?? ""),
    [cookie],
  );
  const hasTracker = Boolean(gaMeasurementId || yandexCounterId);

  useEffect(() => {
    if (consent?.analytics) return;
    stopBrowserAnalytics(gaMeasurementId);
  }, [consent, gaMeasurementId]);

  if (!hasTracker || !consent?.analytics) return null;

  return (
    <>
      {gaMeasurementId ? <GoogleAnalytics gaId={gaMeasurementId} /> : null}
      {yandexCounterId ? <YandexMetrika counterId={yandexCounterId} /> : null}
    </>
  );
}

function YandexMetrika({ counterId }: { counterId: string }) {
  useEffect(() => {
    const numericId = Number(counterId);
    if (!Number.isFinite(numericId) || numericId <= 0) return;

    type YandexQueue = ((...args: unknown[]) => void) & {
      a: unknown[][];
      l: number;
    };
    const w = window as Window & { ym?: YandexQueue };
    const existing = document.querySelector(`script[src="${YANDEX_TAG_SRC}"]`);
    if (!existing) {
      function enqueue(...args: unknown[]): void {
        queue.a.push(args);
      }
      const queue = enqueue as YandexQueue;
      queue.a = [];
      queue.l = Date.now();
      w.ym = w.ym ?? queue;
      const script = document.createElement("script");
      script.async = true;
      script.src = YANDEX_TAG_SRC;
      document.head.appendChild(script);
    }
    w.ym?.(numericId, "init", {
      clickmap: true,
      trackLinks: true,
      accurateTrackBounce: true,
      webvisor: false,
    });
    return () => {
      stopBrowserAnalytics();
    };
  }, [counterId]);

  return <div data-analytics="yandex-metrika" data-counter={counterId} hidden />;
}
