/**
 * Dev-only same-origin hop for browser paths that previously went through Caddy.
 * Without a reverse proxy, Next rewrites `/v1/*` (and API docs paths) to the
 * internal API so OAuth/login/link hrefs stay relative and cookies stay simple.
 * Staging/prod keep Caddy as the public edge (ADR-0044); this hop is not used there.
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
 * Mirrors the path split formerly owned by deploy/caddy/Caddyfile.dev.
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
