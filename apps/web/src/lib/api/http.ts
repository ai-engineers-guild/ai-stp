import { cookies } from "next/headers";

import { CSRF_COOKIE, SESSION_COOKIE } from "@/lib/auth/cookies";
import { getEnv } from "@/lib/env";

import { ApiError, mapHttpError } from "./errors";
import { executeJsonRequest, usesMock, type QueryValue } from "./http-shared";
import { mockFetch, mockResultToData } from "./mock-transport";

export type PrivateRequestOptions = {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  query?: Record<string, QueryValue>;
  headers?: Record<string, string>;
  body?: unknown;
  sessionToken?: string;
};

/**
 * Build request headers for mock vs real API transport.
 *
 * Mock path keeps the historical fake bearer for in-process fixtures.
 * Real path forwards the opaque session cookie and, for mutating methods,
 * the double-submit CSRF value - never a fake Authorization bearer.
 */
async function buildHeaders(
  method: string,
  options: PrivateRequestOptions,
  mock: boolean,
): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(options.headers ?? {}),
  };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  if (mock) {
    if (options.sessionToken) {
      headers["Authorization"] = "Bearer mock-session";
      headers["Cookie"] = `${SESSION_COOKIE}=${options.sessionToken}`;
    }
    return headers;
  }

  const jar = await cookies();
  const session = options.sessionToken ?? jar.get(SESSION_COOKIE)?.value;
  const csrf = jar.get(CSRF_COOKIE)?.value;
  if (session) {
    const parts = [`${SESSION_COOKIE}=${session}`];
    if (csrf) {
      parts.push(`${CSRF_COOKIE}=${csrf}`);
    }
    headers["Cookie"] = parts.join("; ");
  }
  if (method !== "GET" && csrf) {
    headers["X-CSRF-Token"] = csrf;
  }
  return headers;
}

/**
 * Private request-scoped helper. Always `cache: "no-store"`. Reads cookies()
 * for session/CSRF and never shares a response across requests.
 */
export async function privateApiRequest<T>(
  path: string,
  options: PrivateRequestOptions = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const env = getEnv();
  const mock = usesMock(path, env);
  const headers = await buildHeaders(method, options, mock);
  const request: Parameters<typeof executeJsonRequest<T>>[1] = {
    method,
    headers,
    cache: "no-store",
  };
  if (options.query) {
    request.query = options.query;
  }
  if (options.body !== undefined) {
    request.body = options.body;
  }
  return executeJsonRequest<T>(path, request);
}

/** Existing callers keep this name; it is the private helper. */
export const apiRequest = privateApiRequest;

/** Binary POST/PUT (avatar upload) - does not JSON-encode the body. */
export async function apiRequestBinary<T>(
  path: string,
  options: {
    method?: "POST" | "PUT";
    sessionToken?: string;
    contentType: string;
    body: BodyInit;
    headers?: Record<string, string>;
  },
): Promise<T> {
  const method = options.method ?? "POST";
  const env = getEnv();
  const mock = usesMock(path, env);
  if (mock) {
    const mockHeaders: Record<string, string> = {
      "Content-Type": options.contentType,
      ...(options.headers ?? {}),
    };
    if (options.sessionToken) {
      mockHeaders["Authorization"] = "Bearer mock-session";
      mockHeaders["Cookie"] = `${SESSION_COOKIE}=${options.sessionToken}`;
    }
    const mockInit: { headers: Record<string, string>; body?: string } = {
      headers: mockHeaders,
    };
    if (typeof options.body === "string") {
      mockInit.body = options.body;
    }
    const result = mockFetch(method, path, mockInit);
    return mockResultToData<T>(result);
  }

  const requestOptions: PrivateRequestOptions = {};
  if (options.sessionToken) {
    requestOptions.sessionToken = options.sessionToken;
  }
  if (options.headers) {
    requestOptions.headers = options.headers;
  }
  const headers = await buildHeaders(method, requestOptions, false);
  headers["Content-Type"] = options.contentType;
  headers["Accept"] = "application/json";

  const base = env.AI_STP_API_BASE_URL.replace(/\/$/, "");
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      method,
      headers,
      body: options.body,
      cache: "no-store",
    });
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

export async function apiRequestWithMeta<T>(
  path: string,
  options: PrivateRequestOptions = {},
): Promise<{ data: T; operationId: string | null }> {
  const method = options.method ?? "GET";
  const env = getEnv();
  const mock = usesMock(path, env);
  const headers = await buildHeaders(method, options, mock);

  if (mock) {
    const mockInit: { headers: Record<string, string>; body?: string } = { headers };
    if (options.body !== undefined) {
      mockInit.body = JSON.stringify(options.body);
    }
    const result = mockFetch(method, path, mockInit);
    const data = mockResultToData<T>(result);
    return {
      data,
      operationId: result.headers?.["x-operation-id"] ?? null,
    };
  }

  const base = env.AI_STP_API_BASE_URL.replace(/\/$/, "");
  const init: RequestInit = {
    method,
    headers,
    cache: "no-store",
  };
  if (options.body !== undefined) {
    init.body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(`${base}${path}`, init);
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
  return {
    data: body as T,
    operationId: response.headers.get("x-operation-id"),
  };
}

export type { QueryValue };
