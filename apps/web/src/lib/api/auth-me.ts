import { apiRequest } from "@/lib/api/http";

export type AuthMe = {
  account_id: string;
  device_id: string | null;
};

function unwrapData(body: unknown): Record<string, unknown> {
  if (body !== null && typeof body === "object") {
    const record = body as Record<string, unknown>;
    const data = record["data"];
    if (data !== null && typeof data === "object") {
      return data as Record<string, unknown>;
    }
    return record;
  }
  return {};
}

/**
 * Resolve the authenticated account from the opaque server session.
 * Accepts either a CLI success envelope or a bare resource body.
 */
export async function readAuthMe(): Promise<AuthMe> {
  const body = await apiRequest<unknown>("/v1/auth/me");
  const data = unwrapData(body);
  const accountId = data["account_id"];
  if (typeof accountId !== "string" || !accountId.startsWith("account_")) {
    throw new Error("invalid /v1/auth/me payload");
  }
  const deviceId = data["device_id"];
  return {
    account_id: accountId,
    device_id: typeof deviceId === "string" ? deviceId : null,
  };
}
