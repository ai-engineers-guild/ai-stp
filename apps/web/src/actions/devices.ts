"use server";

import { randomBytes } from "node:crypto";
import { revalidatePath } from "next/cache";

import { asDeviceId, asETag } from "@/lib/brands";
import { revokeDevice } from "@/lib/api/devices";
import { ApiError } from "@/lib/api/errors";
import {
  assertCsrf,
  clearSessionCookies,
  readCsrfToken,
  readSession,
  SESSION_COOKIE,
} from "@/lib/auth/session";
import { cookies } from "next/headers";

export async function revokeDeviceAction(input: {
  deviceId: string;
  etag: string;
  csrfToken: string;
}): Promise<{ operationId: string | null; signedOut: boolean }> {
  const cookieCsrf = await readCsrfToken();
  assertCsrf(input.csrfToken, cookieCsrf);

  const session = await readSession();
  if (!session) {
    throw new ApiError({
      code: "AI_STP_UNAUTHORIZED",
      message: "not signed in",
      status: 401,
    });
  }

  const jar = await cookies();
  const sessionToken = jar.get(SESSION_COOKIE)?.value;
  if (!sessionToken) {
    throw new ApiError({
      code: "AI_STP_UNAUTHORIZED",
      message: "not signed in",
      status: 401,
    });
  }

  const deviceId = asDeviceId(input.deviceId);
  const etag = asETag(input.etag);
  const idempotencyKey = randomBytes(16).toString("hex");

  const result = await revokeDevice(sessionToken, deviceId, etag, idempotencyKey);
  const signedOut = session.deviceId === deviceId;
  if (signedOut) {
    await clearSessionCookies();
  }
  revalidatePath("/[locale]/devices", "page");
  return { operationId: result.operationId, signedOut };
}
