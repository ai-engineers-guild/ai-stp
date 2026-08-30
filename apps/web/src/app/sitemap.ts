import type { MetadataRoute } from "next";

import { readSeoSitemapIndex, readSeoSitemapShard, type SeoSubjectKind } from "@/lib/api/seo";
import { PUBLIC_LOCALES, publicOrigin } from "@/lib/site";
import { isFeatureEnabled } from "@/lib/features/gate";
import { listPublishedContent } from "@/lib/api/content";

const PUBLIC_ROUTES = ["", "/catalog", "/docs"] as const;

const SAAS_PUBLIC_ROUTES = [
  "/contact",
  "/legal/privacy",
  "/legal/cookies",
  "/legal/service-rules",
  "/legal/licensing",
] as const;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const origin = publicOrigin();
  const routes = isFeatureEnabled("saas_public_pages")
    ? [...PUBLIC_ROUTES, ...SAAS_PUBLIC_ROUTES]
    : PUBLIC_ROUTES;
  const base = PUBLIC_LOCALES.flatMap((locale) =>
    routes.map((route) => ({
      url: new URL(`/${locale}${route}`, origin).toString(),
      lastModified: new Date("2026-08-09T00:00:00Z"),
      changeFrequency: route === "/catalog" ? ("daily" as const) : ("monthly" as const),
      priority: route === "" ? 1 : route === "/catalog" ? 0.9 : 0.6,
      alternates: {
        languages: Object.fromEntries(
          PUBLIC_LOCALES.map((item) => [item, new URL(`/${item}${route}`, origin).toString()]),
        ),
      },
    })),
  );
  let hubs: MetadataRoute.Sitemap = base;
  if (isFeatureEnabled("content_hub")) {
    const contentPages = await Promise.all(
      PUBLIC_LOCALES.map(async (locale) => {
        const items = await listPublishedContent(locale).catch(() => []);
        return [
          {
            url: new URL(`/${locale}/content`, origin).toString(),
            lastModified: new Date("2026-08-12T00:00:00Z"),
            changeFrequency: "weekly" as const,
            priority: 0.7,
          },
          ...items.map((entry) => ({
            url: new URL(`/${locale}/content/${entry.type}/${entry.slug}`, origin).toString(),
            lastModified: new Date(`${entry.published_at}T00:00:00Z`),
            changeFrequency: "monthly" as const,
            priority: 0.6,
          })),
        ];
      }),
    );
    hubs = [...base, ...contentPages.flat()];
  }
  const catalog = await catalogSitemapEntries();
  return [...hubs, ...catalog];
}

async function catalogSitemapEntries(): Promise<MetadataRoute.Sitemap> {
  const index = await readSeoSitemapIndex();
  if (!index) return [];
  const entries: MetadataRoute.Sitemap = [];
  for (const shardRef of index.shards) {
    const match = /\/sitemaps\/([a-z]+)-(en|ru)-(\d+)\.xml$/.exec(shardRef.loc);
    if (!match) continue;
    const kind = match[1] as SeoSubjectKind;
    const locale = match[2] as "en" | "ru";
    const page = Number(match[3]);
    const shard = await readSeoSitemapShard(kind, locale, page);
    if (!shard) continue;
    for (const item of shard.urls) {
      entries.push({
        url: item.loc,
        lastModified: new Date(item.lastmod),
        alternates: { languages: item.alternates },
      });
    }
  }
  return entries;
}
