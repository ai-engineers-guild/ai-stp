import { notFound } from "next/navigation";

import { readSeoSitemapShard, type SeoSubjectKind } from "@/lib/api/seo";

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export async function GET(_request: Request, context: { params: Promise<{ shard: string }> }) {
  const { shard } = await context.params;
  const match = /^([a-z]+)-(en|ru)-(\d+)\.xml$/.exec(shard);
  if (!match) notFound();
  const kind = match[1] as SeoSubjectKind;
  const locale = match[2] as "en" | "ru";
  const page = Number(match[3]);
  const document = await readSeoSitemapShard(kind, locale, page);
  if (!document) notFound();
  const urls = document.urls
    .map((item) => {
      const alternates = Object.entries(item.alternates)
        .map(
          ([hrefLang, href]) =>
            `    <xhtml:link rel="alternate" hreflang="${escapeXml(hrefLang)}" href="${escapeXml(href)}"/>`,
        )
        .join("\n");
      return `  <url>\n    <loc>${escapeXml(item.loc)}</loc>\n    <lastmod>${escapeXml(item.lastmod.slice(0, 10))}</lastmod>\n${alternates}\n  </url>`;
    })
    .join("\n");
  const body = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">
${urls}
</urlset>
`;
  return new Response(body, {
    headers: {
      "content-type": "application/xml; charset=utf-8",
      "cache-control": "public, max-age=60",
    },
  });
}
