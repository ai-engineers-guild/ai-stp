import { z } from "zod";
import { isUploadedMediaUrl, isGithubRawUrl, isYoutubeVideoId } from "@/lib/component-media";
import { corporateHref } from "@/lib/features/corporate-path";

export type CorporateDetailResource = "teams" | "projects" | "members" | "technologies";

const CORPORATE_ID_SUFFIX = "[0-7][0-9A-HJKMNP-TV-Z]{25}";
const CORPORATE_RESOURCE_ID_PATTERN: Record<CorporateDetailResource, RegExp> = {
  teams: new RegExp(`^operation_${CORPORATE_ID_SUFFIX}$`),
  projects: new RegExp(`^remote_project_${CORPORATE_ID_SUFFIX}$`),
  members: new RegExp(`^account_${CORPORATE_ID_SUFFIX}$`),
  technologies: new RegExp(`^technology_${CORPORATE_ID_SUFFIX}$`),
};

const safeUrl = z
  .string()
  .max(2048)
  .url()
  .refine((value) => {
    const url = new URL(value);
    return /^https:\/\//i.test(value) && !url.username && !url.password;
  });
const assetUrl = z
  .string()
  .refine(
    (value) =>
      /^https:\/\//i.test(value) || /^\/v1\/media\/avatars\/avatar_[a-f0-9]{24}$/.test(value),
  );
const reference = z.object({
  kind: z.enum(["team", "project", "employee", "technology", "component", "setup"]),
  id: z.string().min(1),
  name: z.string().min(1),
});
const profileLinkSchema = z
  .object({ label: z.string().trim().min(1).max(60), url: safeUrl })
  .strict();
const profileMediaSchema = z
  .object({
    kind: z.enum(["image", "video", "youtube"]),
    url: z.string(),
    alt: z.string().min(1).max(240),
    caption: z.string().max(500).default(""),
  })
  .strict();
const profileLinksSchema = z
  .array(profileLinkSchema)
  .max(5)
  .refine((items) => new Set(items.map((item) => item.url)).size === items.length, {
    message: "duplicate link URL",
  });
export const entityProfileFieldsSchema = z
  .object({
    description: z.string().max(20000),
    avatar_asset_id: z
      .string()
      .regex(/^avatar_[a-f0-9]{24}$/)
      .nullable(),
    links: profileLinksSchema,
    media: z.array(profileMediaSchema).max(5),
  })
  .strict();
export const corporatePresentationSchema = z.object({
  name: z.string().trim().min(1).max(200),
  description: z.string().max(20000),
  avatar_asset_id: z
    .string()
    .regex(/^avatar_[a-f0-9]{24}$/)
    .nullable(),
  avatar_url: assetUrl.nullable(),
  links: profileLinksSchema,
  media: z
    .array(
      profileMediaSchema
        .extend({ id: z.string(), source_label: z.string() })
        .refine((item) =>
          item.kind === "youtube"
            ? isYoutubeVideoId(item.url)
            : isUploadedMediaUrl(item.url) ||
              isGithubRawUrl(item.url) ||
              /^\/v1\/media\/avatars\/avatar_[a-f0-9]{24}$/.test(item.url),
        ),
    )
    .max(5),
  revision: z.number().int().nonnegative(),
  authorization_revision: z.number().int().nonnegative(),
  can_edit: z.boolean(),
  owner: reference.nullable(),
  author: reference.nullable(),
  owner_account_id: z.string().nullable().default(null),
  leads: z.array(reference),
  teams: z.array(reference),
  projects: z.array(reference),
  technologies: z.array(reference),
  components: z.array(reference),
});
export const entityProfileViewSchema = z.object({
  name: z.string(),
  revision: z.number().int().nonnegative(),
  can_edit: z.boolean(),
  avatar_url: assetUrl.nullable(),
  owner_account_id: z.string().nullable(),
  fields: entityProfileFieldsSchema,
});

export const entityProfileWriteRequestSchema = z
  .object({
    schema_version: z.literal(1),
    fields: entityProfileFieldsSchema,
    expected_revision: z.number().int().nonnegative(),
    authorization_revision: z.number().int().positive(),
    idempotency_key: z.string().regex(/^[A-Za-z0-9._~-]{16,128}$/),
  })
  .strict();

export function presentationFromProfile(
  value: unknown,
  authorizationRevision: number,
): CorporatePresentation {
  const profile = entityProfileViewSchema.parse(value);
  return corporatePresentationSchema.parse({
    ...profile.fields,
    ...profile,
    authorization_revision: authorizationRevision,
    media: profile.fields.media.map((item, index) => ({
      ...item,
      id: `${index}:${item.url}`,
      source_label: profile.name,
    })),
    owner: null,
    author: null,
    leads: [],
    teams: [],
    projects: [],
    technologies: [],
    components: [],
  });
}
export type CorporatePresentation = z.infer<typeof corporatePresentationSchema>;

export function corporateReferenceHref(ref: z.infer<typeof reference>) {
  const resources = {
    team: "teams",
    project: "projects",
    employee: "members",
    technology: "technologies",
    component: "components",
    setup: "setups",
  };
  return corporateHref(
    `${ref.kind === "component" || ref.kind === "setup" ? "/catalog" : "/corporate"}/${resources[ref.kind]}/${encodeURIComponent(ref.id)}`,
  );
}

export function corporatePresentationPath(
  organizationId: string,
  resource: CorporateDetailResource,
  id: string,
) {
  const resourcePattern = CORPORATE_RESOURCE_ID_PATTERN[resource];
  if (
    !new RegExp(`^organization_${CORPORATE_ID_SUFFIX}$`).test(organizationId) ||
    !resourcePattern.test(id)
  )
    throw new Error("invalid corporate target");
  const kind = {
    teams: "team",
    projects: "project",
    members: "employee",
    technologies: "technology",
  };
  return `/v1/corporate/organizations/${organizationId}/entity-profiles/${kind[resource]}/${id}`;
}
