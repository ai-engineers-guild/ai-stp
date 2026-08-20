import type { MetadataRoute } from "next";

import { PUBLIC_LOCALES, publicOrigin } from "@/lib/site";
import { isFeatureEnabled } from "@/lib/features/gate";
import { publishedContent } from "@/lib/content/source";

const PUBLIC_ROUTES = ["", "/catalog", "/docs"] as const;

const SAAS_PUBLIC_ROUTES = [
  "/contact",
  "/legal/privacy",
  "/legal/cookies",
  "/legal/service-rules",
  "/legal/licensing",
] as const;

export default function sitemap(): MetadataRoute.Sitemap {
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
  if (!isFeatureEnabled("content_hub")) return base;
  return [
    ...base,
    ...PUBLIC_LOCALES.flatMap((locale) => [
      {
        url: new URL(`/${locale}/content`, origin).toString(),
        lastModified: new Date("2026-08-12T00:00:00Z"),
        changeFrequency: "weekly" as const,
        priority: 0.7,
      },
      ...publishedContent(locale).map((entry) => ({
        url: new URL(`/${locale}/content/${entry.type}/${entry.slug}`, origin).toString(),
        lastModified: new Date(`${entry.published_at}T00:00:00Z`),
        changeFrequency: "monthly" as const,
        priority: 0.6,
      })),
    ]),
  ];
}
