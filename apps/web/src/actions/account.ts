"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { z } from "zod";

import {
  unlinkAccountIdentity,
  updateAccountPrivacy,
  type UnlinkProvider,
} from "@/lib/api/account";
import { ApiError } from "@/lib/api/errors";
import { SESSION_COOKIE } from "@/lib/auth/cookies";
import { assertCsrf, readCsrfToken, readSession } from "@/lib/auth/session";

/**
 * Public profile write is not in frozen OpenAPI #71 (SPEC-023 REQ-2303).
 * Kept as an explicit failure so no UI path can invent a success or operation_id
 * (REQ-2309, REQ-2310). Remove when an additive contract route exists.
 */
export async function updatePublicProfileAction(input: {
  csrfToken: string;
  data: unknown;
}): Promise<never> {
  void input;
  // Satisfy require-await while remaining a Server Action (must be async).
  await Promise.resolve();
  throw new ApiError({
    code: "AI_STP_VALIDATION_ERROR",
    message: "public profile write is not available on the frozen /v1 contract",
    status: 400,
  });
}

const unlinkSchema = z.object({
  provider: z.enum(["google", "github"]),
  csrfToken: z.string().min(1),
});

const privacySchema = z.object({
  showProfilePublicly: z.boolean(),
  allowPublisherListing: z.boolean(),
  csrfToken: z.string().min(1),
});

export async function updatePrivacyAction(input: {
  showProfilePublicly: boolean;
  allowPublisherListing: boolean;
  csrfToken: string;
}): Promise<{ ok: true } | { ok: false; message: string }> {
  const parsed = privacySchema.safeParse(input);
  if (!parsed.success) return { ok: false, message: "invalid request" };
  try {
    assertCsrf(parsed.data.csrfToken, await readCsrfToken());
  } catch {
    return { ok: false, message: "csrf failed" };
  }
  const session = await readSession();
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!session || !token) return { ok: false, message: "not signed in" };
  try {
    await updateAccountPrivacy(
      {
        schema_version: 1,
        show_profile_publicly: parsed.data.showProfilePublicly,
        allow_publisher_listing: parsed.data.allowPublisherListing,
      },
      token,
    );
  } catch (error) {
    return { ok: false, message: error instanceof ApiError ? error.message : "save failed" };
  }
  revalidatePath("/[locale]/account/privacy", "page");
  return { ok: true };
}

export async function unlinkIdentityAction(input: {
  provider: UnlinkProvider;
  csrfToken: string;
}): Promise<{ ok: true } | { ok: false; message: string }> {
  const parsed = unlinkSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, message: "invalid request" };
  }
  const cookieCsrf = await readCsrfToken();
  try {
    assertCsrf(parsed.data.csrfToken, cookieCsrf);
  } catch {
    return { ok: false, message: "csrf failed" };
  }
  const session = await readSession();
  if (!session) {
    return { ok: false, message: "not signed in" };
  }
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) {
    return { ok: false, message: "not signed in" };
  }
  try {
    await unlinkAccountIdentity(parsed.data.provider, token);
  } catch (error) {
    if (error instanceof ApiError) {
      return { ok: false, message: error.message };
    }
    return { ok: false, message: "unlink failed" };
  }
  revalidatePath("/[locale]/account", "page");
  revalidatePath("/[locale]/account/privacy", "page");
  return { ok: true };
}
