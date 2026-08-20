import { getEnv, type AppEnv } from "@/lib/env";

import { ApiError, mapHttpError } from "./errors";
import { mockFetch, mockResultToData } from "./mock-transport";

/** Auth surface with no dev-reachable backend (OAuth needs provider credentials). */
const AUTH_MOCK_PREFIXES = ["/v1/auth", "/v1/account", "/v1/devices"] as const;

/**
 * Decide mock vs real per path. `AI_STP_USE_MOCKS` mocks everything (tests, full
 * offline dev). Otherwise the catalog uses the real API and only the auth surface
 * is mocked when `AI_STP_MOCK_AUTH` is set.
 */
export function usesMock(path: string, env: AppEnv): boolean {
  if (env.AI_STP_USE_MOCKS) {
    return true;
  }
  return env.AI_STP_MOCK_AUTH && AUTH_MOCK_PREFIXES.some((prefix) => path.startsWith(prefix));
}

export type QueryValue = string | number | boolean | ReadonlyArray<string> | undefined;

export function buildQuery(query: Record<string, QueryValue> | undefined): URLSearchParams {
  const params = new URLSearchParams();
  if (!query) {
    return params;
  }
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined) {
      continue;
    }
    if (typeof value !== "string" && typeof value !== "number" && typeof value !== "boolean") {
      for (const item of value) {
        params.append(key, item);
      }
      continue;
    }
    params.set(key, String(value));
  }
  return params;
}

export type JsonRequestCache = {
  cache?: RequestCache;
  next?: { revalidate: number };
};

/**
 * JSON transport shared by public and private helpers. Callers own headers
 * and cache mode so credential policy cannot leak across the boundary.
 */
export async function executeJsonRequest<T>(
  path: string,
  options: {
    method: string;
    query?: Record<string, QueryValue>;
    headers: Record<string, string>;
    body?: unknown;
  } & JsonRequestCache,
): Promise<T> {
  const env = getEnv();
  const mock = usesMock(path, env);

  if (mock) {
    const mockInit: { query: URLSearchParams; headers: Record<string, string>; body?: string } = {
      query: buildQuery(options.query),
      headers: options.headers,
    };
    if (options.body !== undefined) {
      mockInit.body = JSON.stringify(options.body);
    }
    return mockResultToData<T>(mockFetch(options.method, path, mockInit));
  }

  const base = env.AI_STP_API_BASE_URL.replace(/\/$/, "");
  const url = new URL(`${base}${path}`);
  for (const [key, value] of buildQuery(options.query).entries()) {
    url.searchParams.append(key, value);
  }

  const init: RequestInit & { next?: { revalidate: number } } = {
    method: options.method,
    headers: options.headers,
  };
  if (options.cache) {
    init.cache = options.cache;
  }
  if (options.next) {
    init.next = options.next;
  }
  if (options.body !== undefined) {
    init.body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new ApiError({
      code: "AI_STP_UNAVAILABLE",
      message: "API unavailable",
      status: 0,
    });
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw mapHttpError(response.status, body, response.headers);
  }
  return body as T;
}
