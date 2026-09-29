"use server";

import { randomBytes } from "node:crypto";
import { revalidatePath } from "next/cache";

import { getTranslations } from "next-intl/server";

import { asDeviceId, asETag } from "@/lib/brands";
import { revokeDevice } from "@/lib/api/devices";
import { ApiError } from "@/lib/api/errors";
import { clearSessionCookies, readSession, requireCsrf, SESSION_COOKIE } from "@/lib/auth/session";
import { cookies } from "next/headers";

export async function revokeDeviceAction(input: {
  deviceId: string;
  etag: string;
  csrfToken: string;
}): Promise<{ operationId: string | null; signedOut: boolean }> {
  await requireCsrf(input.csrfToken);

  const common = await getTranslations("common");
  const session = await readSession();
  if (!session) {
    throw new ApiError({
      code: "AI_STP_UNAUTHORIZED",
      message: common("notSignedIn"),
      status: 401,
    });
  }

  const jar = await cookies();
  const sessionToken = jar.get(SESSION_COOKIE)?.value;
  if (!sessionToken) {
    throw new ApiError({
      code: "AI_STP_UNAUTHORIZED",
      message: common("notSignedIn"),
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
