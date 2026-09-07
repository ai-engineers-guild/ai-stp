/** Accept only a catalog return path in the current locale. */
export function catalogReturnHref(
  value: string | string[] | undefined,
  locale: string,
  fallback: string,
): string {
  if (typeof value !== "string" || !value.startsWith("/") || value.length > 8192) return fallback;
  try {
    const base = "https://catalog.invalid";
    const url = new URL(value, base);
    if (url.origin !== base || !["/catalog", `/${locale}/catalog`].includes(url.pathname)) {
      return fallback;
    }
    return `/catalog${url.search}${url.hash}`;
  } catch {
    return fallback;
  }
}
