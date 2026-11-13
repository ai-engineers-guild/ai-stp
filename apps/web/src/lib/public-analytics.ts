/** Browser analytics IDs and the deployment kill switch.

Empty measurement IDs keep that vendor off. `NEXT_PUBLIC_ANALYTICS_ENABLED=false`
turns both off even when IDs are set. Cookie consent still gates load when
analytics is enabled.
*/
export const YANDEX_TAG_SRC = "https://mc.yandex.ru/metrika/tag.js";

export function publicAnalyticsConfig(env: Record<string, string | undefined> = process.env): {
  enabled: boolean;
  gaMeasurementId: string;
  yandexCounterId: string;
} {
  const enabled = env.NEXT_PUBLIC_ANALYTICS_ENABLED !== "false";
  if (!enabled) {
    return { enabled: false, gaMeasurementId: "", yandexCounterId: "" };
  }
  return {
    enabled: true,
    gaMeasurementId: env.NEXT_PUBLIC_GA_MEASUREMENT_ID?.trim() ?? "",
    yandexCounterId: env.NEXT_PUBLIC_YANDEX_METRIKA_COUNTER_ID?.trim() ?? "",
  };
}

/** Tear down vendor tags and cookies after analytics consent is withdrawn. */
export function stopBrowserAnalytics(gaMeasurementId = ""): void {
  if (typeof document === "undefined") return;
  document.querySelector(`script[src="${YANDEX_TAG_SRC}"]`)?.remove();
  const w = window as Window & { ym?: unknown };
  delete w.ym;
  if (gaMeasurementId) {
    Object.assign(w, { [`ga-disable-${gaMeasurementId}`]: true });
  }
  // Vendors scope their cookies to the registrable domain (`.example.com`),
  // which a host-only deletion does not reach.
  const domains = cookieDomains(location.hostname);
  for (const part of document.cookie.split(";")) {
    const name = part.split("=")[0]?.trim() ?? "";
    if (!name || name === "ai_stp_consent") continue;
    if (/^(_ym_|_ga)/.test(name) || name === "_gid" || name === "_gat") {
      for (const domain of domains) {
        const scope = domain ? `; Domain=${domain}` : "";
        // biome-ignore lint/suspicious/noDocumentCookie: Consent persistence and vendor-cookie removal must remain synchronous before optional analytics runs; see #1404.
        document.cookie = `${name}=; Path=/; Max-Age=0${scope}`;
      }
    }
  }
}

/** The host-only scope followed by every parent domain a page can address. */
export function cookieDomains(hostname: string): string[] {
  const labels = hostname.split(".");
  if (labels.length < 2 || /^[0-9.]+$/.test(hostname) || hostname.includes(":")) return [""];
  return ["", ...labels.slice(0, -1).map((_, index) => `.${labels.slice(index).join(".")}`)];
}
