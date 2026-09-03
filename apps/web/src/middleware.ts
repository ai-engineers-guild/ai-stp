import createMiddleware from "next-intl/middleware";
import { NextRequest, NextResponse } from "next/server";

import enMessages from "../messages/en.json";
import ruMessages from "../messages/ru.json";
import { SESSION_COOKIE } from "@/lib/auth/cookies";
import { docsMarkdownRedirectPath } from "@/lib/docs-nav-path";
import { COMPILED_FEATURES } from "@/lib/features/compiled";
import { routing } from "@/lib/i18n/routing";
import {
  isImpossibleCatalogObjectPath,
  isImpossibleCountryPath,
} from "@/lib/projection/missing-route";
import { parseProjectionRoute, projectionRequestHeaders } from "@/lib/projection/route";

const intlMiddleware = createMiddleware(routing);

/**
 * Edge middleware: locale routing and coarse cookie presence for private
 * routes. The projection is a real route segment (ADR-0076), so nothing is
 * rewritten here; the request only carries its canonical path for chrome that
 * needs to build the paired URL. Cryptographic session validation runs in Node
 * server components (ADR-0041).
 */
export default function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
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
    (contentMatch && !COMPILED_FEATURES.content_hub) ||
    disabledSaasPage ||
    isImpossibleCatalogObjectPath(pathname) ||
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
  const parsed = parseProjectionRoute(pathname);

  // A projection never changes access: private routes keep one session gate.
  if (parsed.isProtected) {
    const raw = request.cookies.get(SESSION_COOKIE)?.value;
    if (!raw) {
      const loginUrl = request.nextUrl.clone();
      loginUrl.pathname = `/${parsed.locale}${parsed.isMachine ? "/ai" : ""}/login`;
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
  );

  return intlMiddleware(
    new NextRequest(request.url, { headers: requestHeaders, method: request.method }),
  );
}

export const config = {
  matcher: ["/", "/(ru|en)/:path*"],
};
