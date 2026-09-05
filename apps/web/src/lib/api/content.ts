import { ApiError } from "./errors";
import { publicApiGet } from "./public-http";

export const CONTENT_TYPES = ["article", "blog_post", "changelog", "release_notes"] as const;
export type ContentType = (typeof CONTENT_TYPES)[number];
export type ContentLocale = "ru" | "en";
export type ContentSourceKind = "repository" | "staff";

export type ContentSummary = {
  schema_version: 1;
  type: ContentType;
  slug: string;
  locale: ContentLocale;
  title: string;
  description: string;
  published_at: string;
  tags: string[];
  revision_id: string;
  content_digest: string;
  source_kind: ContentSourceKind;
  cover_image: string | null;
  cover_alt: string | null;
};

export type ContentDetail = ContentSummary & {
  body: string;
  source_ref: string | null;
  source_path: string | null;
};

export type ContentListResponse = {
  schema_version: 1;
  etag: string;
  items: ContentSummary[];
};

export async function listPublishedContent(locale: string): Promise<ContentSummary[]> {
  const result = await publicApiGet<ContentListResponse>("/v1/content", { query: { locale } });
  return result.items;
}

export async function readPublishedContent(
  locale: string,
  type: string,
  slug: string,
): Promise<ContentDetail | null> {
  try {
    return await publicApiGet<ContentDetail>(`/v1/content/${type}/${slug}`, {
      query: { locale },
    });
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_NOT_FOUND") return null;
    throw error;
  }
}
