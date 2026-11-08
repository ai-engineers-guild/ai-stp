import i18next from "i18next";
import ICU from "i18next-icu";
import { initReactI18next, useTranslation } from "react-i18next";
import { create } from "zustand";
import { readPreference, writePreference } from "./preferences";
import configuration from "./localization.json";
import bootstrap from "./generated/messages-bootstrap.json";
import type en from "./locales/en.json";

export type MessageKey = keyof typeof en;
export type Locale = keyof typeof configuration.languages;
export const languages = configuration.languages;
const fallback = configuration.defaultLocale as Locale;
const loaders = import.meta.glob<Record<string, string>>("./locales/*.json", {
  import: "default",
});
const loading = new Map<Locale, Promise<void>>();

export const i18n = i18next.createInstance();
void i18n
  .use(ICU)
  .use(initReactI18next)
  .init({
    lng: fallback,
    fallbackLng: fallback,
    supportedLngs: Object.keys(languages),
    resources: { [fallback]: { translation: bootstrap } },
    keySeparator: false,
    initAsync: false,
    returnEmptyString: false,
    returnNull: false,
    parseMissingKeyHandler: (key) => {
      throw new Error(`Missing Desktop message: ${key}`);
    },
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
  });

export function isLocale(value: string): value is Locale {
  return Object.hasOwn(languages, value);
}

export function preferredLocale(): Locale {
  const saved = readPreference("ai-stp.locale");
  if (saved && isLocale(saved)) return saved;
  for (const language of globalThis.navigator?.languages ?? []) {
    const candidate = language.toLowerCase();
    if (
      candidate === "zh" ||
      candidate.startsWith("zh-hans") ||
      candidate.startsWith("zh-cn") ||
      candidate.startsWith("zh-sg")
    )
      return "zh-Hans";
    const base = candidate.split("-")[0];
    if (isLocale(base)) return base;
  }
  return fallback;
}

/** Catalogs are packaged assets; no translation service or external request. */
export function loadCatalog(locale: Locale): Promise<void> {
  const pending = loading.get(locale);
  if (pending) return pending;
  const loader = loaders[`./locales/${locale}.json`];
  const request = (async () => {
    if (!loader) throw new Error(`Missing packaged Desktop catalog: ${locale}`);
    i18n.addResourceBundle(locale, "translation", await loader(), true, true);
  })().catch((error: unknown) => {
    loading.delete(locale);
    throw error;
  });
  loading.set(locale, request);
  return request;
}

interface LocaleState {
  locale: Locale;
  pending: boolean;
  failed: boolean;
}
export const useLocale = create<LocaleState>(() => ({
  locale: fallback,
  pending: false,
  failed: false,
}));
let generation = 0;
i18n.on("languageChanged", (value) => {
  if (!isLocale(value)) return;
  if (typeof document !== "undefined") {
    document.documentElement.lang = value;
    document.documentElement.dir = languages[value].direction;
  }
  useLocale.setState({ locale: value });
});

/** A preference change never remounts a form or changes an operation's owner. */
export async function changeLocale(
  locale: Locale,
  persist = true,
): Promise<boolean> {
  const request = ++generation;
  useLocale.setState({ pending: true, failed: false });
  try {
    await loadCatalog(locale);
    if (request !== generation) return false;
    await i18n.changeLanguage(locale);
    if (request !== generation) return false;
    if (persist) writePreference("ai-stp.locale", locale);
    useLocale.setState({ pending: false });
    return true;
  } catch {
    if (request === generation)
      useLocale.setState({ pending: false, failed: true });
    return false;
  }
}

export async function prepareLocale(): Promise<void> {
  const locale = preferredLocale();
  if (locale !== fallback) await changeLocale(locale, false);
  if (typeof document !== "undefined") {
    document.documentElement.lang = useLocale.getState().locale;
    document.documentElement.dir =
      languages[useLocale.getState().locale].direction;
  }
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat(i18n.resolvedLanguage ?? fallback).format(value);
}

export function formatDateTime(value: string | number): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(i18n.resolvedLanguage ?? fallback, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatTime(value: number): string {
  return new Intl.DateTimeFormat(i18n.resolvedLanguage ?? fallback, {
    timeStyle: "medium",
  }).format(value);
}

export function useText() {
  const { t } = useTranslation(undefined, { i18n });
  return (key: MessageKey, values?: Record<string, string | number>) =>
    t(key, values);
}
