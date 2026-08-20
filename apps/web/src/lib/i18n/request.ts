import { getRequestConfig } from "next-intl/server";

import { type AppLocale, defaultLocale, locales, routing } from "./routing";

function isAppLocale(value: string): value is AppLocale {
  return (locales as readonly string[]).includes(value);
}

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale: AppLocale = requested && isAppLocale(requested) ? requested : defaultLocale;

  const catalog = (await import(`../../../messages/${locale}.json`)) as {
    default: Record<string, unknown>;
  };
  return {
    locale,
    messages: catalog.default,
  };
});

export { routing };
