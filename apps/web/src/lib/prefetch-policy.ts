/**
 * Router prefetch rule (SPEC-048 REQ-4805, ADR-0095).
 *
 * Explicit prefetch stays on a small stable shell. Private pages, catalog
 * filter/pagination, and high-cardinality object/version/publisher links set
 * prefetch={false}. Other cheap links may omit the prop.
 */

export const SHELL_PREFETCH_HREFS = [
  "/",
  "/catalog",
  "/services",
  "/content",
  "/contact",
  "/login",
] as const;

export function hrefPathname(href: string): string {
  const [path] = href.split("?");
  return path || "/";
}

export function isShellPrefetchHref(href: string): boolean {
  if (href.includes("?")) {
    return false;
  }
  return (SHELL_PREFETCH_HREFS as readonly string[]).includes(hrefPathname(href));
}
