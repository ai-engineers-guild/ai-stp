import { defineRouting } from "next-intl/routing";

export const locales = ["ru", "en"] as const;
export type AppLocale = (typeof locales)[number];
export const defaultLocale: AppLocale = "ru";

/** The one check for a `[locale]` segment or a requested locale. */
export function isAppLocale(value: string | undefined): value is AppLocale {
  return value !== undefined && (locales as readonly string[]).includes(value);
}

export const routing = defineRouting({
  locales,
  defaultLocale,
  localePrefix: "always",
});
