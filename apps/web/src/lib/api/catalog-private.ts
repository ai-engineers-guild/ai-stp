import { privateApiRequest, type QueryValue } from "./http";

export function catalogPrivateGet<T>(
  path: string,
  sessionToken: string,
  query?: Record<string, QueryValue>,
): Promise<T> {
  return privateApiRequest<T>(path, { sessionToken, ...(query ? { query } : {}) });
}
