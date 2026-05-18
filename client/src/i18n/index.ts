import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import en from "@/i18n/locales/en.json";
import zh from "@/i18n/locales/zh.json";

// Single source of truth for runtime translations.
// - `lng` is auto-detected (querystring `?lng=zh|en`, then localStorage, then
//   browser nav language). We default to `zh` because the project is operated
//   primarily in Chinese.
// - `keySeparator` is `.` and `nsSeparator` is `:` (default), so JSON nesting
//   maps cleanly: `t('map.coordinates')`.
// - `returnNull: false` makes missing keys fall through to the key string,
//   which surfaces missing translations during development.
void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      zh: { translation: zh },
    },
    fallbackLng: "zh",
    supportedLngs: ["zh", "en"],
    interpolation: {
      escapeValue: false, // React already escapes by default
    },
    detection: {
      order: ["querystring", "localStorage", "navigator"],
      lookupQuerystring: "lng",
      lookupLocalStorage: "panopticon.lng",
      caches: ["localStorage"],
    },
    returnNull: false,
  });

export default i18n;
