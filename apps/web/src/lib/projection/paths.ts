import type { Projection } from "@/lib/projection/mode";

/**
 * Build the paired human or machine URL for a path.
 * Accepts absolute paths with or without locale, and relative page paths.
 * Safe for client and server (no next/headers).
 */
export function pairedPath(pathname: string, mode: Projection, locale: string): string {
  if (pathname.startsWith("http://") || pathname.startsWith("https://")) {
    return pathname;
  }
  const parts = pathname.split("/").filter(Boolean);

  let pathLocale = locale;
  if (parts[0] === locale || parts[0] === "en" || parts[0] === "ru") {
    pathLocale = parts.shift() ?? locale;
  }

  if (parts[0] === "ai") {
    parts.shift();
  }

  if (mode === "machine") {
    parts.unshift("ai");
  }

  parts.unshift(pathLocale);
  return "/" + parts.join("/");
}

/**
 * First segments that belong to the localized page tree. Everything else -
 * API endpoints such as /v1/auth/..., static machine surfaces, asset paths -
 * is not a page and must never be rewritten into the projection.
 */
const PAGE_SEGMENTS = new Set([
  "access",
  "account",
  "catalog",
  "contact",
  "content",
  "device-login",
  "devices",
  "docs",
  "invitations",
  "legal",
  "login",
  "objects",
  "publications",
  "publishers",
  "reports",
  "services",
  "countries",
  "staff",
]);

/** A localized page path, as opposed to an API endpoint or a static file. */
export function isPagePath(href: string): boolean {
  if (href.startsWith("http://") || href.startsWith("https://")) return false;
  if (!href.startsWith("/")) return false;
  const parts = href.split(/[?#]/)[0]?.split("/").filter(Boolean) ?? [];
  if (parts.length === 0) return true;
  const withoutLocale = parts[0] === "en" || parts[0] === "ru" ? parts.slice(1) : parts;
  const head = withoutLocale[0];
  if (head === undefined) return true;
  return PAGE_SEGMENTS.has(head === "ai" ? (withoutLocale[1] ?? "") : head);
}

/**
 * Link target inside a machine document. Every page has a machine
 * representation, so internal page links stay in the machine projection
 * (REQ-3607). Non-page targets - API endpoints, static files, absolute URLs -
 * are left untouched: projecting them would break the request they serve.
 */
export function projectedHref(href: string, locale: string): string {
  if (!isPagePath(href)) return href;
  return pairedPath(href, "machine", locale);
}

export function pathWithoutLocale(canonicalPathname: string, locale: string): string {
  const parts = canonicalPathname.split("/").filter(Boolean);
  if (parts[0] === locale) {
    parts.shift();
  }
  if (parts[0] === "ai") {
    parts.shift();
  }
  return parts.length === 0 ? "/" : "/" + parts.join("/");
}

/** True when the localized or unlocalized path is already a machine URL. */
export function isMachinePagePath(pathname: string): boolean {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "en" || parts[0] === "ru") {
    parts.shift();
  }
  return parts[0] === "ai";
}

function querySuffix(search: string): string {
  if (!search) return "";
  return search.startsWith("?") ? search : `?${search}`;
}

/**
 * Human/Machine switch targets for the current page. The pair is derived from
 * the live pathname so a shared layout cannot keep a stale catalog href after
 * client navigation to a component or version page (REQ-3604, REQ-3624).
 */
export function projectionSwitchHrefs(
  pathname: string,
  locale: string,
  search = "",
): { humanHref: string; machineHref: string } {
  const query = querySuffix(search);
  return {
    humanHref: `${pairedPath(pathname, "human", locale)}${query}`,
    machineHref: `${pairedPath(pathname, "machine", locale)}${query}`,
  };
}
