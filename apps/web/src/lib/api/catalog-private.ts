import { privateApiRequest } from "./http";

export function catalogPrivateGet<T>(path: string, sessionToken: string): Promise<T> {
  return privateApiRequest<T>(path, { sessionToken });
}
