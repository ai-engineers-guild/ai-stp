/** Accept only a local catalog or owner-workspace return path. */
export function catalogReturnHref(
  value: string | string[] | undefined,
  locale: string,
  fallback: string,
): string {
  if (typeof value !== "string" || !value.startsWith("/") || value.length > 8192) return fallback;
  try {
    const base = "https://catalog.invalid";
    const url = new URL(value, base);
    const allowed = ["/catalog", `/${locale}/catalog`, "/objects", `/${locale}/objects`];
    if (url.origin !== base || !allowed.includes(url.pathname)) {
      return fallback;
    }
    const pathname = url.pathname.endsWith("/objects") ? "/objects" : "/catalog";
    return `${pathname}${url.search}${url.hash}`;
  } catch {
    return fallback;
  }
}
