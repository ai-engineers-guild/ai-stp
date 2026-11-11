import { headers } from "next/headers";
import { LOCALE_HEADER } from "@/lib/projection/route";

import { getRequestConfig } from "next-intl/server";

import { type AppLocale, defaultLocale, isAppLocale, routing } from "./routing";

export default getRequestConfig(async ({ locale: explicitLocale }) => {
  const requested = explicitLocale ?? (await headers()).get(LOCALE_HEADER) ?? undefined;
  const locale: AppLocale = isAppLocale(requested) ? requested : defaultLocale;

  const catalog = (await import(`../../../messages/${locale}.json`)) as {
    default: Record<string, unknown>;
  };
  return {
    locale,
    messages: catalog.default,
    timeZone: "UTC",
  };
});

export { routing };
