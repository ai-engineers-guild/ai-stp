import type { MetadataRoute } from "next";

import { publicOrigin } from "@/lib/site";
import { isFeatureEnabled } from "@/lib/features/gate";

export default function robots(): MetadataRoute.Robots {
  const origin = publicOrigin();
  return {
    rules: [
      {
        userAgent: "*",
        allow: [
          "/",
          "/ru/",
          "/en/",
          "/ru/catalog",
          "/en/catalog",
          "/llms.txt",
          ...(isFeatureEnabled("content_hub") ? ["/ru/content", "/en/content", "/feed.xml"] : []),
        ],
        disallow: [
          "/api/",
          "/ru/account",
          "/en/account",
          "/ru/devices",
          "/en/devices",
          "/ru/objects",
          "/en/objects",
          "/ru/likes",
          "/en/likes",
          "/ru/reports",
          "/en/reports",
          "/ru/staff",
          "/en/staff",
          ...(!isFeatureEnabled("content_hub") ? ["/ru/content", "/en/content", "/feed.xml"] : []),
          ...(!isFeatureEnabled("saas_public_pages")
            ? ["/ru/contact", "/en/contact", "/ru/legal", "/en/legal"]
            : []),
        ],
      },
    ],
    sitemap: new URL("/sitemap.xml", origin).toString(),
    host: origin.origin,
  };
}
