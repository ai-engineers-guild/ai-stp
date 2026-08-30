"""Generation-aware sitemap shards. Jobs never append a shared file."""

from __future__ import annotations

from collections.abc import Sequence
from xml.sax.saxutils import escape

from ai_stp_contracts.seo import SEO_SITEMAP_SHARD_LIMIT, SeoSitemapShard, SeoSitemapUrl
from ai_stp_platform.seo.metrics import record_sitemap_generation
from ai_stp_platform.seo.urls import sitemap_shard_url


def split_urls(
    urls: Sequence[SeoSitemapUrl], limit: int = SEO_SITEMAP_SHARD_LIMIT
) -> list[list[SeoSitemapUrl]]:
    if limit < 1:
        raise ValueError("shard limit must be positive")
    return [list(urls[index : index + limit]) for index in range(0, len(urls), limit)] or [[]]


def render_urlset(urls: Sequence[SeoSitemapUrl]) -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]
    for item in urls:
        parts.append("  <url>")
        parts.append(f"    <loc>{escape(item.loc)}</loc>")
        parts.append(f"    <lastmod>{escape(item.lastmod[:10])}</lastmod>")
        for locale, href in sorted(item.alternates.items()):
            hreflang = escape(locale)
            href_xml = escape(href)
            parts.append(
                f'    <xhtml:link rel="alternate" hreflang="{hreflang}" href="{href_xml}"/>'
            )
        parts.append("  </url>")
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"


def render_sitemap_index(origin: str, shards: Sequence[SeoSitemapShard], lastmod: str) -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for shard in shards:
        loc = sitemap_shard_url(origin, shard.kind, shard.locale, shard.page)
        parts.append("  <sitemap>")
        parts.append(f"    <loc>{escape(loc)}</loc>")
        parts.append(f"    <lastmod>{escape(lastmod[:10])}</lastmod>")
        parts.append("  </sitemap>")
    parts.append("</sitemapindex>")
    record_sitemap_generation(generation=shards[0].generation if shards else 0, cache_age_seconds=0)
    return "\n".join(parts) + "\n"
