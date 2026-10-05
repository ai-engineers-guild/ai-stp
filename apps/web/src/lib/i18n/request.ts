import { getRequestConfig } from "next-intl/server";

import { type AppLocale, defaultLocale, isAppLocale, routing } from "./routing";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale: AppLocale = isAppLocale(requested) ? requested : defaultLocale;

  const catalog = (await import(`../../../messages/${locale}.json`)) as {
    default: Record<string, unknown>;
  };
  return {
    locale,
    messages: catalog.default,
  };
});

export { routing };
