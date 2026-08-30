import type { Metadata } from "next";

import type { SeoPublicProfile } from "@/lib/api/seo";
import { SITE_NAME } from "@/lib/site";

export function metadataFromSeo(profile: SeoPublicProfile | null, fallback: Metadata): Metadata {
  if (!profile) {
    return {
      ...fallback,
      robots: { index: true, follow: true },
    };
  }
  const index = profile.profile.robots === "index,follow";
  const author = jsonLdAuthor(profile.profile.json_ld);
  const openGraphType =
    fallback.openGraph && "type" in fallback.openGraph ? fallback.openGraph.type : "website";
  return {
    title: { absolute: profile.profile.title },
    description: profile.profile.description,
    alternates: {
      canonical: profile.profile.canonical_url,
      languages: { ...profile.profile.alternates, "x-default": profile.profile.canonical_url },
    },
    ...(author ? { authors: [{ name: author }], creator: author } : {}),
    robots: { index, follow: true },
    openGraph: {
      type: openGraphType,
      siteName: SITE_NAME,
      title: profile.profile.social.title,
      description: profile.profile.social.description,
      url: profile.profile.canonical_url,
      locale: profile.profile.social.locale === "ru" ? "ru_RU" : "en_US",
      images: [
        {
          url: profile.profile.social.image_url,
          width: 1200,
          height: 630,
          alt: profile.profile.social.image_alt,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: profile.profile.social.title,
      description: profile.profile.social.description,
      images: [{ url: profile.profile.social.image_url, alt: profile.profile.social.image_alt }],
    },
  };
}

function jsonLdAuthor(jsonLd: Record<string, unknown>): string | null {
  const graph = jsonLd["@graph"];
  if (!Array.isArray(graph)) return null;
  const nodes: unknown[] = graph;
  const author = nodes.find(
    (item): item is Record<string, unknown> => isJsonObject(item) && item["@type"] === "Person",
  );
  return typeof author?.name === "string" && author.name.trim() ? author.name : null;
}

function isJsonObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function versionPageMetadata(canonical: string, title?: string): Metadata {
  return {
    ...(title ? { title } : {}),
    alternates: { canonical },
    robots: { index: false, follow: true },
  };
}
