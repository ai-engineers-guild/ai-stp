import createMiddleware from "next-intl/middleware";
import { NextRequest, NextResponse } from "next/server";

import enMessages from "../messages/en.json";
import ruMessages from "../messages/ru.json";
import { SESSION_COOKIE } from "@/lib/auth/cookies";
import { docsMarkdownRedirectPath } from "@/lib/docs-nav-path";
import { COMPILED_FEATURES, COMPILED_FEATURE_PROFILE } from "@/lib/features/compiled";
import { corporateHref, corporateSharedPath } from "@/lib/features/corporate-path";
import { routing } from "@/lib/i18n/routing";
import {
  isImpossibleCatalogObjectPath,
  isImpossibleCountryPath,
} from "@/lib/projection/missing-route";
import { parseProjectionRoute, projectionRequestHeaders } from "@/lib/projection/route";

const intlProxy = createMiddleware(routing);

function isLoopbackHostname(hostname: string): boolean {
  return ["localhost", "127.0.0.1", "[::1]", "::1"].includes(hostname.toLowerCase());
}

/** Keep NextURL's loopback normalization from turning an internal rewrite into a proxy hop. */
function requestOriginUrl(request: NextRequest) {
  const url = request.nextUrl.clone();
  const rawHost = request.headers.get("host");
  if (!rawHost || !isLoopbackHostname(url.hostname)) return url;
  try {
    const candidate = new URL(`http://${rawHost}`);
    if (
      !candidate.username &&
      !candidate.password &&
      candidate.pathname === "/" &&
      !candidate.search &&
      !candidate.hash &&
      candidate.port === url.port &&
      isLoopbackHostname(candidate.hostname)
    ) {
      url.host = candidate.host;
    }
  } catch {
    // Ignore malformed host headers and keep NextURL's validated origin.
  }
  return url;
}

/**
 * Accept pages must render unauthenticated: the invitation token lives in the
 * URL fragment, which this gate never sees, so a login redirect here would
 * destroy it. The accept POST enforces the session itself; a 401 sends the
 * client to login with the fragment carried inside `returnTo`. Machine
 * projections stay rejected — the `/ai/` segment does not match.
 */
const INVITATION_ACCEPT_PATH =
  /^\/(?:en|ru)\/(?:corporate\/)?(?:corporate-)?invitations\/[^/]+(?:\/confirm)?$/;

function isBlockedPath(pathname: string, sharedPath: string | null): boolean {
  const contentMatch = pathname.match(/^\/(?:ru|en)\/(?:ai\/)?content(?:\/|$)/);
  const disabledSaasPage =
    !COMPILED_FEATURES.saas_public_pages &&
    /^\/(?:ru|en)\/(?:ai\/)?(?:contact|legal(?:\/|$))/.test(pathname);
  return (
    (COMPILED_FEATURE_PROFILE === "corporate_hub" &&
      /^\/(?:ru|en)\/(?:ai\/)?(?:services|countries)(?:\/|$)/.test(pathname)) ||
    (contentMatch && !COMPILED_FEATURES.content_hub) ||
    disabledSaasPage ||
    isImpossibleCatalogObjectPath(sharedPath ?? pathname) ||
    isImpossibleCountryPath(pathname)
  );
}

/**
 * Edge middleware: locale routing and coarse cookie presence for private
 * routes. The projection is a real route segment (ADR-0076); only the explicit
 * corporate shared-page compatibility aliases below rewrite to their physical
 * shared route. Cryptographic session validation runs in Node server components
 * (ADR-0041).
 */
const LEGACY_ADMIN_SEGMENTS: Record<string, string> = {
  access: "access-model",
  audit: "audit",
  employees: "employee-access",
  "job-titles": "job-titles",
  members: "employee-access",
  roles: "roles",
  security: "security",
  "tech-categories": "tech-categories",
};

/** The `admins` tree moved to named organization pages; member detail lands in the drawer. */
function legacyAdminRedirect(request: NextRequest, pathname: string) {
  const match = pathname.match(
    /^(\/(?:en|ru)(?:\/ai)?)\/corporate\/organization\/admins(?:\/([^/?]+))?(?:\/([^/?]+))?\/?$/,
  );
  if (!match) return null;
  const [, prefix, segment, tail] = match;
  const target = segment === undefined ? "members" : LEGACY_ADMIN_SEGMENTS[segment];
  if (
    target === undefined ||
    (tail !== undefined && segment !== "employees" && segment !== "members")
  )
    return null;
  const url = requestOriginUrl(request);
  const invitations = url.searchParams.get("tab") === "invitations";
  url.pathname = `${prefix}/corporate/admin/${invitations ? "invitations" : target}`;
  if (invitations) url.searchParams.delete("tab");
  if (tail !== undefined) url.searchParams.set("employee", tail);
  return NextResponse.redirect(url, 308);
}

const LEGACY_ORG_ADMIN_PAGES = new Set([
  "access-model",
  "audit",
  "employee-access",
  "invitations",
  "job-titles",
  "members",
  "roles",
  "security",
  "tech-categories",
]);

/**
 * The administration pages lived one generation under
 * `/corporate/organization/{page}` before moving to `/corporate/admin/{page}`.
 * Employee tails resolve to the directory drawer in one hop.
 */
function legacyOrgAdminRedirect(request: NextRequest, pathname: string) {
  const match = pathname.match(
    /^(\/(?:en|ru)(?:\/ai)?)\/corporate\/organization\/([^/?]+)(?:\/([^/?]+))?\/?$/,
  );
  if (!match) return null;
  const [, prefix, segment, tail] = match;
  if (!LEGACY_ORG_ADMIN_PAGES.has(segment ?? "")) return null;
  if (tail !== undefined && segment !== "employee-access") return null;
  const url = requestOriginUrl(request);
  const invitations = segment === "members" && url.searchParams.get("tab") === "invitations";
  url.pathname = invitations
    ? `${prefix}/corporate/admin/invitations`
    : `${prefix}/corporate/admin/${segment}`;
  if (invitations) url.searchParams.delete("tab");
  if (tail !== undefined) url.searchParams.set("employee", tail);
  return NextResponse.redirect(url, 308);
}

/** Permanent redirects for retired corporate paths; checked before routing. */
function corporateLegacyRedirect(request: NextRequest, pathname: string) {
  const legacyAdmin = legacyAdminRedirect(request, pathname);
  if (legacyAdmin) return legacyAdmin;
  const legacyOrgAdmin = legacyOrgAdminRedirect(request, pathname);
  if (legacyOrgAdmin) return legacyOrgAdmin;
  const adminsIndex = pathname.match(/^(\/(?:en|ru)(?:\/ai)?)\/corporate\/admins?\/?$/);
  if (adminsIndex) {
    const url = requestOriginUrl(request);
    url.pathname = `${adminsIndex[1]}/corporate/admin/members`;
    return NextResponse.redirect(url, 308);
  }
  const legacyCorporatePublisher = pathname.match(
    /^(\/(?:en|ru)(?:\/ai)?)\/corporate\/publishers(?:\/([^/]+))?$/,
  );
  if (legacyCorporatePublisher) {
    const url = requestOriginUrl(request);
    url.pathname = `${legacyCorporatePublisher[1]}/corporate/employees${
      legacyCorporatePublisher[2] ? `/${legacyCorporatePublisher[2]}` : ""
    }`;
    return NextResponse.redirect(url, 308);
  }
  const legacyCorporateCatalog = pathname.match(/^(\/(?:en|ru)(?:\/ai)?)\/corporate\/components$/);
  if (legacyCorporateCatalog) {
    const url = requestOriginUrl(request);
    url.pathname = `${legacyCorporateCatalog[1]}/corporate/catalog`;
    return NextResponse.redirect(url, 308);
  }
  return null;
}

export default function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const legacy = corporateLegacyRedirect(request, pathname);
  if (legacy) return legacy;
  const sharedPath =
    COMPILED_FEATURE_PROFILE === "corporate_hub" ? corporateSharedPath(pathname) : null;
  if (COMPILED_FEATURE_PROFILE === "corporate_hub" && !sharedPath) {
    const match = pathname.match(/^(\/(?:en|ru)(?:\/ai)?)(\/.*)?$/);
    if (match) {
      const page = match[2] || "/";
      const destination = corporateHref(page);
      if (destination !== page) {
        const url = requestOriginUrl(request);
        url.pathname = `${match[1]}${destination}`;
        return NextResponse.redirect(url);
      }
    }
  }
  const docsMarkdown = docsMarkdownRedirectPath(pathname);
  if (docsMarkdown) {
    const url = request.nextUrl.clone();
    url.pathname = docsMarkdown;
    return NextResponse.redirect(url);
  }
  if (isBlockedPath(pathname, sharedPath)) {
    const language = pathname.startsWith("/ru/") ? "ru" : "en";
    const messages = language === "ru" ? ruMessages : enMessages;
    const title = messages.errors.notFoundTitle;
    return new NextResponse(
      `<!doctype html><html lang="${language}"><head><meta charset="utf-8"><meta name="robots" content="noindex"><title>${title}</title></head><body><main><h1>${title}</h1></main></body></html>`,
      {
        status: 404,
        headers: {
          "content-type": "text/html; charset=utf-8",
          "cache-control": "public, max-age=300",
        },
      },
    );
  }
  const parsed = parseProjectionRoute(sharedPath ?? pathname);

  // The corporate hub is fully authenticated: only the login surfaces stay
  // public. Session expiry is validated server-side in the site layout.
  const corporateSessionRequired =
    COMPILED_FEATURE_PROFILE === "corporate_hub" &&
    parsed.canonicalPage !== "login" &&
    parsed.canonicalPage !== "device-login";

  // A projection never changes access: private routes keep one session gate.
  // Invitation accept pages are the exception — the fragment token they carry
  // cannot survive a server-side login redirect (INVITATION_ACCEPT_PATH).
  const sessionGated =
    (parsed.isProtected || corporateSessionRequired) && !INVITATION_ACCEPT_PATH.test(pathname);
  if (sessionGated) {
    const raw = request.cookies.get(SESSION_COOKIE)?.value;
    if (!raw) {
      const loginUrl = requestOriginUrl(request);
      loginUrl.pathname = `/${parsed.locale}${parsed.isMachine ? "/ai" : ""}${corporateHref("/login")}`;
      loginUrl.search = "";
      loginUrl.searchParams.set("returnTo", `${pathname}${request.nextUrl.search}`);
      return NextResponse.redirect(loginUrl);
    }
  }

  const requestHeaders = projectionRequestHeaders(
    request.headers,
    parsed.projection,
    parsed.canonicalPathname,
    request.nextUrl.search,
    parsed.locale,
  );
  requestHeaders.set("x-ai-stp-request-pathname", pathname);

  if (sharedPath) {
    const url = requestOriginUrl(request);
    url.pathname = sharedPath;
    return NextResponse.rewrite(url, { request: { headers: requestHeaders } });
  }

  return intlProxy(
    new NextRequest(request.url, { headers: requestHeaders, method: request.method }),
  );
}

export const config = {
  matcher: ["/", "/(ru|en)/:path*"],
};
