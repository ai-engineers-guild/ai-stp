import { beforeEach, describe, expect, it, vi } from "vitest";
import enMessages from "../../messages/en.json";
import ruMessages from "../../messages/ru.json";

const { requestHeaders } = vi.hoisted(() => ({
  requestHeaders: vi.fn<() => Promise<Headers>>(),
}));
vi.mock("next/headers", () => ({ headers: requestHeaders }));
// The server-only next-intl wrapper returns its callback unchanged.
vi.mock("next-intl/server", () => ({ getRequestConfig: <T>(callback: T) => callback }));

import requestConfig from "@/lib/i18n/request";
import { LOCALE_HEADER } from "@/lib/projection/route";

function configInput(locale?: string) {
  return {
    ...(locale === undefined ? {} : { locale }),
    get requestLocale(): Promise<string | undefined> {
      throw new Error("The obsolete locale cache must not be read");
    },
  };
}

beforeEach(() => requestHeaders.mockReset());

describe("request translation locale", () => {
  it.each(["ru", "en"])("uses the proxy's %s locale for pages and actions", async (locale) => {
    requestHeaders.mockResolvedValue(new Headers({ [LOCALE_HEADER]: locale }));
    const config = await requestConfig(configInput());
    expect(config.locale).toBe(locale);
    expect(config.messages).toEqual(locale === "ru" ? ruMessages : enMessages);
  });

  it("honors an explicit locale without reading request headers", async () => {
    const config = await requestConfig(configInput("en"));
    expect(config.locale).toBe("en");
    expect(requestHeaders).not.toHaveBeenCalled();
  });

  it.each([undefined, "unsupported"])(
    "keeps the default for a missing or invalid locale",
    async (locale) => {
      requestHeaders.mockResolvedValue(
        new Headers(locale === undefined ? {} : { [LOCALE_HEADER]: locale }),
      );
      const config = await requestConfig(configInput());
      expect(config.locale).toBe("ru");
    },
  );
});
