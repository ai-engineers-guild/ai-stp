"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { ApiError } from "@/lib/api/errors";
import { updateOwnerPresentation } from "@/lib/api/owner";
import { isGithubRawUrl, isUploadedMediaUrl, isYoutubeVideoId } from "@/lib/component-media";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { assertCsrf, readCsrfToken } from "@/lib/auth/session";

const mediaSchema = z
  .object({
    kind: z.enum(["image", "video", "youtube"]),
    url: z.string().min(1).max(2048),
    alt: z.string().min(1).max(240),
    caption: z.string().max(500),
  })
  .superRefine((item, ctx) => {
    if (item.kind === "youtube") {
      if (!isYoutubeVideoId(item.url)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "youtube media requires an 11-character video id",
          path: ["url"],
        });
      }
      return;
    }
    if (!isUploadedMediaUrl(item.url) && !isGithubRawUrl(item.url)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "image and video require upload path or pinned GitHub raw URL",
        path: ["url"],
      });
    }
  });

const inputSchema = z.object({
  csrfToken: z.string().min(1),
  stableId: z.string().min(8).max(64),
  locale: z.string().min(2).max(5),
  bio: z.string().max(2000),
  media: z.array(mediaSchema).max(5),
});

export async function updateObjectPresentationAction(input: unknown) {
  const parsed = inputSchema.safeParse(input);
  if (!parsed.success) return { ok: false as const, message: "Invalid presentation data." };
  try {
    assertCsrf(parsed.data.csrfToken, await readCsrfToken());
  } catch {
    return { ok: false as const, message: "The form expired. Reload the page." };
  }
  const token = await sessionCookieValue();
  if (!token) return { ok: false as const, message: "Not signed in." };
  try {
    await updateOwnerPresentation(token, parsed.data.stableId, {
      bio: parsed.data.bio,
      media: parsed.data.media,
    });
  } catch (error) {
    return {
      ok: false as const,
      message: error instanceof ApiError ? error.message : "Could not save presentation.",
    };
  }
  revalidatePath(`/${parsed.data.locale}/objects/component/${parsed.data.stableId}`);
  revalidatePath(`/${parsed.data.locale}/objects/component/${parsed.data.stableId}/edit`);
  revalidatePath(`/${parsed.data.locale}/catalog/components/${parsed.data.stableId}`);
  revalidatePath(`/${parsed.data.locale}/catalog`);
  return { ok: true as const };
}
