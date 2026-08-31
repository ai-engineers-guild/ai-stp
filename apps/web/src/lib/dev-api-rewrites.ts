/**
 * Dev-only same-origin hop for browser paths that go through the host proxy in prod.
 * Without a reverse proxy, Next rewrites `/v1/*` (and API docs paths) to the
 * internal API so OAuth/login/link hrefs stay relative and cookies stay simple.
 * Prod keeps the host's nginx as the public edge (ADR-0135); this hop is not used there.
 */

export type RewriteRule = {
  source: string;
  destination: string;
};

/** True only for `next dev` (NODE_ENV=development). */
export function shouldEnableDevApiRewrites(nodeEnv: string | undefined): boolean {
  return nodeEnv === "development";
}

/**
 * Build rewrite rules that proxy browser-facing API paths to AI_STP_API_BASE_URL.
 * Mirrors the path split deploy/nginx/ai-stp.conf.template owns in prod.
 */
export function buildDevApiRewrites(apiBaseUrl: string): RewriteRule[] {
  const base = apiBaseUrl.replace(/\/$/, "");
  return [
    { source: "/v1/:path*", destination: `${base}/v1/:path*` },
    { source: "/docs", destination: `${base}/docs` },
    { source: "/docs/:path*", destination: `${base}/docs/:path*` },
    { source: "/redoc", destination: `${base}/redoc` },
    { source: "/redoc/:path*", destination: `${base}/redoc/:path*` },
    { source: "/openapi.json", destination: `${base}/openapi.json` },
    {
      source: "/schemas/provider-protocol/:path*",
      destination: `${base}/schemas/provider-protocol/:path*`,
    },
  ];
}

/** Resolve rewrite list for Next config from process env. */
export function resolveDevApiRewrites(
  nodeEnv: string | undefined,
  apiBaseUrl: string | undefined,
): RewriteRule[] {
  if (!shouldEnableDevApiRewrites(nodeEnv)) {
    return [];
  }
  const base = (apiBaseUrl ?? "http://localhost:8000").trim();
  if (!base) {
    return [];
  }
  return buildDevApiRewrites(base);
}
