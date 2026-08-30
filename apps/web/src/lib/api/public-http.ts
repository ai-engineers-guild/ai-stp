import { getEnv } from "@/lib/env";

import {
  assertNoCredentialHeaders,
  assertPublicGetPath,
  PUBLIC_CATALOG_REVALIDATE_SECONDS,
} from "./cache-policy";
import { executeJsonRequest, type QueryValue } from "./http-shared";

export type PublicGetHeaders = Record<string, string> & {
  Cookie?: never;
  cookie?: never;
  Authorization?: never;
  authorization?: never;
  "X-CSRF-Token"?: never;
  "x-csrf-token"?: never;
};

/**
 * Public GET options. Type-level surface rejects session tokens and
 * credential headers; runtime checks enforce the same boundary.
 */
export type PublicGetOptions = {
  query?: Record<string, QueryValue>;
  headers?: PublicGetHeaders;
};

function asPlainHeaders(headers: PublicGetHeaders | undefined): Record<string, string> | undefined {
  if (!headers) {
    return undefined;
  }
  return { ...headers };
}

/**
 * Anonymous catalog/public-profile GET. Does not import next/headers, does not
 * accept session or CSRF, and uses the single short revalidate policy.
 */
export async function publicApiGet<T>(path: string, options: PublicGetOptions = {}): Promise<T> {
  assertPublicGetPath(path);
  if ("sessionToken" in options) {
    throw new Error("publicApiGet rejected sessionToken");
  }
  const headers = asPlainHeaders(options.headers);
  assertNoCredentialHeaders(headers);
  const requestHeaders: Record<string, string> = {
    Accept: "application/json",
    ...(headers ?? {}),
  };
  const request: Parameters<typeof executeJsonRequest<T>>[1] = {
    method: "GET",
    headers: requestHeaders,
    cache: "force-cache",
    next: { revalidate: PUBLIC_CATALOG_REVALIDATE_SECONDS },
  };
  if (options.query) {
    request.query = options.query;
  }
  return executeJsonRequest<T>(path, request);
}

/**
 * Anonymous GET that must not be reused from the RSC catalog cache.
 * Used for on-demand GitHub metadata (SPEC-049).
 */
export async function publicApiGetLive<T>(
  path: string,
  options: PublicGetOptions = {},
): Promise<T> {
  assertPublicGetPath(path);
  if ("sessionToken" in options) {
    throw new Error("publicApiGet rejected sessionToken");
  }
  const headers = asPlainHeaders(options.headers);
  assertNoCredentialHeaders(headers);
  const request: Parameters<typeof executeJsonRequest<T>>[1] = {
    method: "GET",
    headers: {
      Accept: "application/json",
      ...(headers ?? {}),
    },
    cache: "no-store",
  };
  if (options.query) {
    request.query = options.query;
  }
  return executeJsonRequest<T>(path, request);
}

/**
 * Anonymous binary GET for immutable OG images. Same public cache boundary.
 */
export async function publicApiGetBytes(
  path: string,
  options: PublicGetOptions = {},
): Promise<ArrayBuffer> {
  assertPublicGetPath(path);
  if ("sessionToken" in options) {
    throw new Error("publicApiGet rejected sessionToken");
  }
  const headers = asPlainHeaders(options.headers);
  assertNoCredentialHeaders(headers);
  const env = getEnv();
  const base = env.AI_STP_API_BASE_URL.replace(/\/$/, "");
  const url = new URL(`${base}${path}`);
  const response = await fetch(url, {
    method: "GET",
    headers: { Accept: "image/png", ...(headers ?? {}) },
    cache: "force-cache",
    next: { revalidate: PUBLIC_CATALOG_REVALIDATE_SECONDS },
  });
  if (!response.ok) {
    throw new Error(`public binary GET failed: ${response.status}`);
  }
  return response.arrayBuffer();
}
