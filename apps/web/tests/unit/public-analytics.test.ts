import { describe, expect, it } from "vitest";

import { cookieDomains, publicAnalyticsConfig, stopBrowserAnalytics } from "@/lib/public-analytics";

describe("publicAnalyticsConfig", () => {
  it("keeps empty defaults off and can disable even when ids are set", () => {
    expect(publicAnalyticsConfig({})).toEqual({
      enabled: true,
      gaMeasurementId: "",
      yandexCounterId: "",
    });
    expect(
      publicAnalyticsConfig({
        NEXT_PUBLIC_ANALYTICS_ENABLED: "false",
        NEXT_PUBLIC_GA_MEASUREMENT_ID: "G-TEST",
        NEXT_PUBLIC_YANDEX_METRIKA_COUNTER_ID: "12345678",
      }),
    ).toEqual({ enabled: false, gaMeasurementId: "", yandexCounterId: "" });
  });

  it("clears injected vendor tags after analytics is withdrawn", () => {
    const script = document.createElement("script");
    script.src = "https://mc.yandex.ru/metrika/tag.js";
    document.head.appendChild(script);
    Object.assign(window, { ym: () => undefined, "ga-disable-G-TEST": false });
    document.cookie = "_ym_uid=1; Path=/";
    stopBrowserAnalytics("G-TEST");
    expect(document.querySelector('script[src="https://mc.yandex.ru/metrika/tag.js"]')).toBeNull();
    expect("ym" in window).toBe(false);
    expect((window as Window & { ["ga-disable-G-TEST"]?: boolean })["ga-disable-G-TEST"]).toBe(
      true,
    );
  });

  it("deletes vendor cookies at every domain scope the page can address", () => {
    expect(cookieDomains("app.aiguild.space")).toEqual([
      "",
      ".app.aiguild.space",
      ".aiguild.space",
    ]);
    expect(cookieDomains("localhost")).toEqual([""]);
    expect(cookieDomains("127.0.0.1")).toEqual([""]);
    const written: string[] = [];
    const descriptor = Object.getOwnPropertyDescriptor(Document.prototype, "cookie");
    Object.defineProperty(document, "cookie", {
      configurable: true,
      get: () => "_ga=GA1.1.1; ai_stp_consent=v1.none; theme=dark",
      set: (value: string) => written.push(value),
    });
    try {
      stopBrowserAnalytics();
    } finally {
      if (descriptor) Object.defineProperty(document, "cookie", descriptor);
    }
    const scopes = cookieDomains(location.hostname);
    expect(written).toEqual(
      scopes.map((domain) => `_ga=; Path=/; Max-Age=0${domain ? `; Domain=${domain}` : ""}`),
    );
  });

  it("passes through measurement ids when analytics is not disabled", () => {
    expect(
      publicAnalyticsConfig({
        NEXT_PUBLIC_GA_MEASUREMENT_ID: " G-TEST ",
        NEXT_PUBLIC_YANDEX_METRIKA_COUNTER_ID: " 12345678 ",
      }),
    ).toEqual({
      enabled: true,
      gaMeasurementId: "G-TEST",
      yandexCounterId: "12345678",
    });
  });
});
