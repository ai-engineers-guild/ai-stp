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

const intlMiddleware = createMiddleware(routing);

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
 * Edge middleware: locale routing and coarse cookie presence for private
 * routes. The projection is a real route segment (ADR-0076); only the explicit
 * corporate shared-page compatibility aliases below rewrite to their physical
 * shared route. Cryptographic session validation runs in Node server components
 * (ADR-0041).
 */
export default function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const legacyCorporateCatalog = pathname.match(/^(\/(?:en|ru)(?:\/ai)?)\/corporate\/components$/);
  if (legacyCorporateCatalog) {
    const url = requestOriginUrl(request);
    url.pathname = `${legacyCorporateCatalog[1]}/corporate/catalog`;
    return NextResponse.redirect(url, 308);
  }
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
  const contentMatch = pathname.match(/^\/(?:ru|en)\/(?:ai\/)?content(?:\/|$)/);
  const disabledSaasPage =
    !COMPILED_FEATURES.saas_public_pages &&
    /^\/(?:ru|en)\/(?:ai\/)?(?:contact|legal(?:\/|$))/.test(pathname);
  if (
    (COMPILED_FEATURE_PROFILE === "corporate_hub" &&
      /^\/(?:ru|en)\/(?:ai\/)?(?:services|countries)(?:\/|$)/.test(pathname)) ||
    (contentMatch && !COMPILED_FEATURES.content_hub) ||
    disabledSaasPage ||
    isImpossibleCatalogObjectPath(sharedPath ?? pathname) ||
    isImpossibleCountryPath(pathname)
  ) {
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

  // A projection never changes access: private routes keep one session gate.
  if (parsed.isProtected) {
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

  if (sharedPath) {
    const url = requestOriginUrl(request);
    url.pathname = sharedPath;
    return NextResponse.rewrite(url, { request: { headers: requestHeaders } });
  }

  return intlMiddleware(
    new NextRequest(request.url, { headers: requestHeaders, method: request.method }),
  );
}

export const config = {
  matcher: ["/", "/(ru|en)/:path*"],
};
