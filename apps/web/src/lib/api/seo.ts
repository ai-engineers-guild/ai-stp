import { publicApiGet } from "./public-http";
import { ApiError } from "./errors";

export type SeoLocale = "ru" | "en";
export type SeoSubjectKind = "component" | "setup" | "article" | "service" | "country";

export type SeoPublicProfile = {
  schema_version: 1;
  revision_id: string;
  snapshot_id: string;
  generation: number;
  etag: string;
  profile: {
    canonical_url: string;
    title: string;
    description: string;
    heading: string;
    summary: string;
    robots: "index,follow" | "noindex,follow";
    alternates: Record<string, string>;
    json_ld: Record<string, unknown>;
    social: {
      title: string;
      description: string;
      image_url: string;
      image_alt: string;
      locale: SeoLocale;
    };
    sections: Array<{ id: string; heading: string; body: string; provenance: string }>;
    internal_links: Array<{ rel: string; href: string; text: string }>;
    breadcrumbs: Array<{ rel: string; href: string; text: string }>;
    index_decision: { eligible: boolean; reasons: string[] };
    modified_at: string;
    published_at: string;
  };
};

export type SeoIndexResponse = {
  schema_version: 1;
  generation: number;
  etag: string;
  shards: Array<{ loc: string; lastmod: string }>;
};

export type SeoSitemapShard = {
  schema_version: 1;
  generation: number;
  kind: SeoSubjectKind;
  locale: SeoLocale;
  page: number;
  urls: Array<{ loc: string; lastmod: string; alternates: Record<string, string> }>;
};

export type SeoCatalogPage = {
  schema_version: 1;
  generation: number;
  items: Array<{
    kind: SeoSubjectKind;
    subject_id: string;
    locale: SeoLocale;
    canonical_url: string;
    title: string;
    description: string;
    markdown_url: string;
    revision_id: string;
    modified_at: string;
  }>;
  page: { next_cursor: string | null; page_size: number };
};

export async function readSeoProfile(
  kind: SeoSubjectKind,
  subjectId: string,
  locale: string,
): Promise<SeoPublicProfile | null> {
  try {
    return await publicApiGet<SeoPublicProfile>(`/v1/seo/subjects/${kind}/${subjectId}`, {
      query: { schema_version: 1, locale },
    });
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_NOT_FOUND") return null;
    return null;
  }
}

export async function readSeoSitemapIndex(): Promise<SeoIndexResponse | null> {
  try {
    return await publicApiGet<SeoIndexResponse>("/v1/seo/sitemap");
  } catch {
    return null;
  }
}

export async function readSeoSitemapShard(
  kind: SeoSubjectKind,
  locale: SeoLocale,
  page: number,
): Promise<SeoSitemapShard | null> {
  try {
    return await publicApiGet<SeoSitemapShard>(`/v1/seo/sitemaps/${kind}/${locale}/${page}`);
  } catch {
    return null;
  }
}

export async function readSeoCatalog(query: {
  locale?: SeoLocale;
  kind?: SeoSubjectKind;
  cursor?: string;
  page_size?: number;
}): Promise<SeoCatalogPage | null> {
  try {
    return await publicApiGet<SeoCatalogPage>("/v1/seo/catalog", {
      query: { schema_version: 1, ...query },
    });
  } catch {
    return null;
  }
}
