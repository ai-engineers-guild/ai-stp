import i18next from "i18next";
import ICU from "i18next-icu";
import { initReactI18next, useTranslation } from "react-i18next";
import en from "./locales/en.json";

export type MessageKey = keyof typeof en;

export const i18n = i18next.createInstance();
// All resources are bundled. Rendering never needs a translation service.
void i18n
  .use(ICU)
  .use(initReactI18next)
  .init({
    lng: "en",
    fallbackLng: "en",
    resources: { en: { translation: en } },
    keySeparator: false,
    initAsync: false,
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
  });

export function useText() {
  const { t } = useTranslation(undefined, { i18n });
  return (key: MessageKey, values?: Record<string, string | number>) =>
    t(key, values);
}
