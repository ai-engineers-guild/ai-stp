import { routing } from "@/lib/i18n/routing";

export const PROTECTED_SEGMENTS = new Set([
  "account",
  "devices",
  "objects",
  "access",
  "publications",
  "invitations",
  "reports",
  "staff",
]);

export const PROJECTION_HEADER = "x-projection";
export const PATHNAME_HEADER = "x-pathname";
export const SEARCH_HEADER = "x-search";
export const LOCALE_HEADER = "X-NEXT-INTL-LOCALE";
export type ParsedProjectionRoute = {
  isLocale: boolean;
  isMachine: boolean;
  isProtected: boolean;
  locale: string;
  canonicalPathname: string;
  canonicalPage: string | undefined;
  projection: "human" | "machine";
};

export function isAppLocale(value: string | undefined): value is (typeof routing.locales)[number] {
  return value !== undefined && (routing.locales as readonly string[]).includes(value);
}

/** Parse a request pathname into projection routing decisions (REQ-3602). */
export function parseProjectionRoute(pathname: string): ParsedProjectionRoute {
  const segments = pathname.split("/").filter(Boolean);
  const maybeLocale = segments[0];
  const isLocale = isAppLocale(maybeLocale);
  const isMachine = isLocale && segments[1] === "ai";

  const canonicalSegments = isMachine ? [segments[0], ...segments.slice(2)] : segments;
  const canonicalPathname = "/" + canonicalSegments.join("/");
  const canonicalPage = isLocale ? canonicalSegments[1] : canonicalSegments[0];
  const isProtected = canonicalPage !== undefined && PROTECTED_SEGMENTS.has(canonicalPage);
  const locale = isLocale ? maybeLocale : routing.defaultLocale;

  return {
    isLocale,
    isMachine,
    isProtected,
    locale,
    canonicalPathname,
    canonicalPage,
    projection: isMachine ? "machine" : "human",
  };
}

/** Build request headers that override any client-supplied projection. */
export function projectionRequestHeaders(
  source: Headers,
  projection: "human" | "machine",
  canonicalPathname: string,
  search: string,
  locale?: string,
): Headers {
  const headers = new Headers(source);
  headers.delete(PROJECTION_HEADER);
  headers.set(PROJECTION_HEADER, projection);
  headers.set(PATHNAME_HEADER, canonicalPathname);
  headers.set(SEARCH_HEADER, search);
  if (locale) {
    headers.set(LOCALE_HEADER, locale);
  }
  return headers;
}
