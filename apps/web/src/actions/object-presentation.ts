"use server";

import { revalidatePath } from "next/cache";
import { getTranslations } from "next-intl/server";
import { z } from "zod";

import { ApiError } from "@/lib/api/errors";
import { fieldErrorsFromDetails, fieldErrorsFromIssues } from "@/lib/api/field-errors";
import { deleteOwnerObject, updateOwnerPresentation } from "@/lib/api/owner";
import {
  isExternalMediaUrl,
  isGithubRawUrl,
  isUploadedMediaUrl,
  isYoutubeVideoId,
  normalizeYoutubeUrl,
} from "@/lib/component-media";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { assertCsrf, readCsrfToken } from "@/lib/auth/session";

type ObjectsTranslator = Awaited<ReturnType<typeof getTranslations<"objects">>>;

function mediaSchema(t: ObjectsTranslator) {
  return z
    .object({
      kind: z.enum(["image", "video", "youtube"]),
      url: z.string().min(1).max(2048),
      alt: z.string().max(240),
      caption: z.string().max(500),
    })
    .superRefine((item, ctx) => {
      if (item.kind === "youtube") {
        if (!normalizeYoutubeUrl(item.url) && !isYoutubeVideoId(item.url)) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: t("mediaYoutubeInvalid"),
            path: ["url"],
          });
        }
        return;
      }
      if (
        !isUploadedMediaUrl(item.url) &&
        !isGithubRawUrl(item.url) &&
        !isExternalMediaUrl(item.url)
      ) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: t("mediaSourceInvalid"),
          path: ["url"],
        });
      }
    });
}

function inputSchema(t: ObjectsTranslator) {
  return z.object({
    csrfToken: z.string().min(1),
    stableId: z.string().min(8).max(64),
    objectKind: z.enum(["component", "setup"]).default("component"),
    locale: z.string().min(2).max(5),
    bio: z.string().max(2000),
    media: z.array(mediaSchema(t)).max(5),
  });
}

export async function updateObjectPresentationAction(input: unknown) {
  const t = await getTranslations("objects");
  const common = await getTranslations("common");
  const parsed = inputSchema(t).safeParse(input);
  if (!parsed.success) {
    const fieldErrors = fieldErrorsFromIssues(parsed.error.issues);
    return {
      ok: false as const,
      code: "CLIENT_VALIDATION_ERROR",
      message: t("fixHighlightedFields"),
      fieldErrors,
    };
  }
  try {
    assertCsrf(parsed.data.csrfToken, await readCsrfToken());
  } catch {
    return {
      ok: false as const,
      code: "CSRF_ERROR",
      message: common("formExpired"),
      fieldErrors: {},
    };
  }
  const token = await sessionCookieValue();
  if (!token) {
    return {
      ok: false as const,
      code: "UNAUTHENTICATED",
      message: common("notSignedIn"),
      fieldErrors: {},
    };
  }
  try {
    await updateOwnerPresentation(
      token,
      parsed.data.stableId,
      {
        bio: parsed.data.bio,
        media: parsed.data.media,
      },
      parsed.data.objectKind,
    );
  } catch (error) {
    const fieldErrors =
      error instanceof ApiError ? fieldErrorsFromDetails(error.details, error.message) : {};
    return {
      ok: false as const,
      code: error instanceof ApiError ? error.code : "PRESENTATION_SAVE_FAILED",
      message:
        Object.keys(fieldErrors).length > 0
          ? Object.entries(fieldErrors)
              .map(([path, message]) => `${path}: ${message}`)
              .join("; ")
          : error instanceof ApiError
            ? error.message
            : t("presentationSaveFailed"),
      fieldErrors,
    };
  }
  revalidatePath(
    `/${parsed.data.locale}/objects/${parsed.data.objectKind}/${parsed.data.stableId}`,
  );
  revalidatePath(
    `/${parsed.data.locale}/objects/${parsed.data.objectKind}/${parsed.data.stableId}/edit`,
  );
  revalidatePath(
    `/${parsed.data.locale}/catalog/${parsed.data.objectKind === "component" ? "components" : "setups"}/${parsed.data.stableId}`,
  );
  revalidatePath(`/${parsed.data.locale}/catalog`);
  return { ok: true as const };
}

const deleteSchema = z.object({
  csrfToken: z.string().min(1),
  stableId: z.string().min(8).max(64),
  objectKind: z.enum(["component", "setup"]),
  locale: z.string().min(2).max(5),
});

export async function deleteObjectAction(input: unknown) {
  const t = await getTranslations("objects");
  const common = await getTranslations("common");
  const parsed = deleteSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false as const, message: t("invalidDeleteRequest") };
  }
  try {
    assertCsrf(parsed.data.csrfToken, await readCsrfToken());
  } catch {
    return { ok: false as const, message: common("formExpired") };
  }
  const token = await sessionCookieValue();
  if (!token) {
    return { ok: false as const, message: common("notSignedIn") };
  }
  try {
    await deleteOwnerObject(token, parsed.data.objectKind, parsed.data.stableId);
  } catch (error) {
    return {
      ok: false as const,
      message: error instanceof ApiError ? error.message : t("deleteFailed"),
    };
  }
  revalidatePath(`/${parsed.data.locale}/catalog`);
  return { ok: true as const };
}
