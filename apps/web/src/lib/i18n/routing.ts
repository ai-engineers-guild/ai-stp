import { defineRouting } from "next-intl/routing";

export const locales = ["ru", "en"] as const;
export type AppLocale = (typeof locales)[number];
export const defaultLocale: AppLocale = "ru";

export const routing = defineRouting({
  locales,
  defaultLocale,
  localePrefix: "always",
});

export function isAppLocale(value: string): value is AppLocale {
  return (locales as readonly string[]).includes(value);
}
