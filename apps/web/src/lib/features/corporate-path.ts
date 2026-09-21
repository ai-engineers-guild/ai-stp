import { COMPILED_FEATURE_PROFILE } from "./compiled";

const SHARED_PAGE =
  /^\/(catalog|account|objects|assigned|likes|devices|access|reports|publications|invitations|onboarding|publishers|login|device-login)(?:\/|[?#]|$)/;

/** Keep shared pages in the corporate URL space without duplicating their UI. */
export function corporateHref(href: string): string {
  if (COMPILED_FEATURE_PROFILE !== "corporate_hub") return href;
  const suffixIndex = href.search(/[?#]/);
  const pathname = suffixIndex === -1 ? href : href.slice(0, suffixIndex);
  const suffix = suffixIndex === -1 ? "" : href.slice(suffixIndex);
  const localized = pathname.match(/^(\/(?:en|ru))(\/ai)?(\/.*)?$/);
  const prefix = localized ? `${localized[1]}${localized[2] ?? ""}` : "";
  const page = localized ? (localized[3] ?? "/") : pathname;
  if (page === "/") return `${prefix}/corporate/overview${suffix}`;
  if (page === "/publishers" || page.startsWith("/publishers/")) {
    return `${prefix}/corporate/employees${page.slice("/publishers".length)}${suffix}`;
  }
  if (page === "/corporate/publishers" || page.startsWith("/corporate/publishers/")) {
    return `${prefix}/corporate/employees${page.slice("/corporate/publishers".length)}${suffix}`;
  }
  if (page === "/corporate" || page.startsWith("/corporate/")) return href;
  return SHARED_PAGE.test(page) ? `${prefix}/corporate${page}${suffix}` : href;
}

export function corporateSharedPath(pathname: string): string | null {
  const match = pathname.match(/^(\/(?:en|ru)(?:\/ai)?)\/corporate(\/.*)$/);
  // The corporate catalog owns its index page so its corporate facets are not
  // silently replaced by the public catalog. Detail pages remain shared.
  if (match?.[2] === "/catalog") return null;
  return match?.[2] && SHARED_PAGE.test(match[2]) ? `${match[1]}${match[2]}` : null;
}
