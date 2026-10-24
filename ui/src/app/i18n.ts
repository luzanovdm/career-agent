import i18next from "i18next";
import { initReactI18next } from "react-i18next";
export interface LocaleCatalog {
  locale: string;
  plural_categories: string[];
  messages: Record<string, string | Record<string, string>>;
}
function resources(catalog: LocaleCatalog) {
  const entries: Record<string, string> = {};
  for (const [key, value] of Object.entries(catalog.messages)) {
    if (typeof value === "string") entries[key] = value;
    else
      for (const [category, message] of Object.entries(value))
        entries[`${key}_${category}`] = message;
  }
  return entries;
}
export async function initializeLocale(
  catalog: LocaleCatalog,
  fallback?: LocaleCatalog,
) {
  await i18next.use(initReactI18next).init({
    lng: catalog.locale,
    fallbackLng: "en",
    keySeparator: false,
    resources: {
      ...(fallback ? { en: { translation: resources(fallback) } } : {}),
      [catalog.locale]: { translation: resources(catalog) },
    },
    interpolation: { escapeValue: false, prefix: "{", suffix: "}" },
    returnEmptyString: false,
    react: { useSuspense: false },
  });
}
export async function applyLocale(catalog: LocaleCatalog) {
  i18next.addResourceBundle(
    catalog.locale,
    "translation",
    resources(catalog),
    true,
    true,
  );
  await i18next.changeLanguage(catalog.locale);
  document.documentElement.lang = catalog.locale;
  document.documentElement.dir = /^(ar|fa|he|ur)(-|$)/i.test(catalog.locale)
    ? "rtl"
    : "ltr";
}
export async function loadInitialLocale() {
  const fallback = (await fetch("/locales/en.json", { cache: "no-cache" }).then(
    (r) => r.json(),
  )) as LocaleCatalog;
  const locale = document.documentElement.dataset.uiLocale ?? "en";
  const catalog = locale.startsWith("ru")
    ? ((await fetch("/locales/ru.json", { cache: "no-cache" }).then((r) =>
        r.json(),
      )) as LocaleCatalog)
    : fallback;
  await initializeLocale(catalog, fallback);
}
export function t(
  key: string,
  values: Record<string, string | number> = {},
): string {
  return String(i18next.t(key, values));
}
export function number(value: number) {
  return new Intl.NumberFormat(i18next.language || "en").format(value);
}
export function date(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf())
    ? value
    : new Intl.DateTimeFormat(i18next.language || "en", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(parsed);
}
export function issueText(issue: { code: string; message?: string }) {
  const key = `issue.${issue.code}`;
  return i18next.exists(key)
    ? t(key)
    : t("issue.generic", { code: issue.code });
}
export function errorText(error: Error & { code?: string; status?: number }) {
  if (error.code) return issueText({ code: error.code });
  return t("error.operation");
}
