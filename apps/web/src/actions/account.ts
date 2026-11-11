"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { getTranslations } from "next-intl/server";
import { z } from "zod";

import {
  unlinkAccountIdentity,
  updateAccountPrivacy,
  type UnlinkProvider,
} from "@/lib/api/account";
import { ApiError } from "@/lib/api/errors";
import { SESSION_COOKIE } from "@/lib/auth/cookies";
import { assertCsrf, readCsrfToken, readSession } from "@/lib/auth/session";

const unlinkSchema = z.object({
  provider: z.enum(["google", "github", "authentik", "keycloak", "gitlab"]),
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
  const common = await getTranslations("common");
  const t = await getTranslations("account");
  const parsed = privacySchema.safeParse(input);
  if (!parsed.success) return { ok: false, message: common("invalidRequest") };
  try {
    assertCsrf(parsed.data.csrfToken, await readCsrfToken());
  } catch {
    return { ok: false, message: common("formExpired") };
  }
  const session = await readSession();
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!session || !token) return { ok: false, message: common("notSignedIn") };
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
    return {
      ok: false,
      message: error instanceof ApiError ? error.message : t("privacySaveFailed"),
    };
  }
  revalidatePath("/[locale]/account/privacy", "page");
  return { ok: true };
}

export async function unlinkIdentityAction(input: {
  provider: UnlinkProvider;
  csrfToken: string;
}): Promise<{ ok: true } | { ok: false; message: string }> {
  const common = await getTranslations("common");
  const t = await getTranslations("account");
  const parsed = unlinkSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, message: common("invalidRequest") };
  }
  const cookieCsrf = await readCsrfToken();
  try {
    assertCsrf(parsed.data.csrfToken, cookieCsrf);
  } catch {
    return { ok: false, message: common("formExpired") };
  }
  const session = await readSession();
  if (!session) {
    return { ok: false, message: common("notSignedIn") };
  }
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) {
    return { ok: false, message: common("notSignedIn") };
  }
  try {
    await unlinkAccountIdentity(parsed.data.provider, token);
  } catch (error) {
    if (error instanceof ApiError) {
      return { ok: false, message: error.message };
    }
    return { ok: false, message: t("unlinkFailed") };
  }
  revalidatePath("/[locale]/account", "page");
  revalidatePath("/[locale]/account/privacy", "page");
  return { ok: true };
}
