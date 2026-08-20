/**
 * Public catalog fetch cache (SPEC-048, ADR-0095).
 *
 * One short TTL applies to allowlisted anonymous GET paths only.
 * Private, mutation, binary, and operation-meta helpers never import this
 * module for their request cache mode.
 */

export const PUBLIC_CATALOG_REVALIDATE_SECONDS = 60;

const PUBLIC_GET_PATHS: readonly RegExp[] = [
  /^\/v1\/catalog\/services$/,
  /^\/v1\/catalog\/services\/[^/?]+$/,
  /^\/v1\/catalog\/countries\/[^/?]+$/,
  /^\/v1\/catalog\/components$/,
  /^\/v1\/catalog\/components\/[^/?]+$/,
  /^\/v1\/catalog\/components\/[^/?]+\/versions\/[^/?]+$/,
  /^\/v1\/catalog\/components\/[^/?]+\/versions\/[^/?]+\/github-metadata$/,
  /^\/v1\/catalog\/setups$/,
  /^\/v1\/catalog\/setups\/[^/?]+$/,
  /^\/v1\/catalog\/setups\/[^/?]+\/versions\/[^/?]+$/,
  /^\/v1\/catalog\/setups\/[^/?]+\/versions\/[^/?]+\/github-metadata$/,
  /^\/v1\/catalog\/setups\/[^/?]+\/versions\/[^/?]+\/context-budget$/,
  /^\/v1\/publishers\/[^/?]+$/,
];

const FORBIDDEN_PUBLIC_HEADER_NAMES = new Set(["cookie", "authorization", "x-csrf-token"]);

export function isPublicCatalogGetPath(path: string): boolean {
  const pathname = path.split("?")[0] ?? path;
  return PUBLIC_GET_PATHS.some((pattern) => pattern.test(pathname));
}

export function assertPublicGetPath(path: string): void {
  if (!isPublicCatalogGetPath(path)) {
    throw new Error(`publicApiGet rejected a non-allowlisted path: ${path.split("?")[0] ?? path}`);
  }
}

export function hasForbiddenPublicHeader(headers: Record<string, string> | undefined): boolean {
  if (!headers) {
    return false;
  }
  return Object.keys(headers).some((name) => FORBIDDEN_PUBLIC_HEADER_NAMES.has(name.toLowerCase()));
}

export function assertNoCredentialHeaders(headers: Record<string, string> | undefined): void {
  if (hasForbiddenPublicHeader(headers)) {
    throw new Error("publicApiGet rejected credential-bearing headers");
  }
}
