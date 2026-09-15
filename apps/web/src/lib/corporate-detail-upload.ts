import { z } from "zod";
import { corporatePresentationPath, type CorporateDetailResource } from "@/lib/corporate-detail";
import { validateComponentMediaFile } from "@/lib/component-media";

const avatarAssetIdSchema = z.string().regex(/^avatar_[a-f0-9]{24}$/);
const uploadSchema = z
  .object({
    schema_version: z.literal(1),
    avatar_asset_id: avatarAssetIdSchema,
    media_id: z.string().min(1).max(64),
    public_url: z.string().regex(/^\/v1\/media\/avatars\/avatar_[a-f0-9]{24}$/),
    state: z.literal("ready"),
    size_bytes: z.number().int().positive(),
    kind: z.enum(["image", "video"]),
  })
  .refine((value) => value.public_url.endsWith(`/${value.avatar_asset_id}`), {
    message: "inconsistent media receipt",
  });

/** Binary upload uses the same-origin corporate BFF, avoiding multipart action limits. */
export async function uploadCorporateDetailMedia(
  input: {
    organizationId: string;
    resource: CorporateDetailResource;
    resourceId: string;
    csrfToken: string;
    purpose: "avatar" | "media";
    expectedRevision: number;
    authorizationRevision: number;
    idempotencyKey: string;
  },
  file: File,
) {
  if (
    validateComponentMediaFile(file) ||
    (input.purpose === "avatar" &&
      (!["image/png", "image/jpeg", "image/webp"].includes(file.type) ||
        file.size > 5 * 1024 * 1024))
  )
    throw new Error("invalid media upload");
  const path = corporatePresentationPath(input.organizationId, input.resource, input.resourceId)
    .replace("/v1/corporate/", "/api/corporate/")
    .replace("/entity-profiles/", "/profiles/");
  const query = new URLSearchParams({
    purpose: input.purpose,
    expected_revision: String(input.expectedRevision),
    authorization_revision: String(input.authorizationRevision),
  });
  const response = await fetch(`${path}/media?${query.toString()}`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": file.type,
      "X-CSRF-Token": input.csrfToken,
      "Idempotency-Key": input.idempotencyKey,
    },
    body: file,
  });
  if (!response.ok) throw new Error("media upload failed");
  const result = uploadSchema.parse(await response.json());
  if (input.purpose === "avatar" && result.kind !== "image") {
    throw new Error("invalid media upload response");
  }
  return result;
}
