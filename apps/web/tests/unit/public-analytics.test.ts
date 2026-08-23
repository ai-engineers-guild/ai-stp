import { describe, expect, it } from "vitest";

import { publicAnalyticsConfig, stopBrowserAnalytics } from "@/lib/public-analytics";

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
