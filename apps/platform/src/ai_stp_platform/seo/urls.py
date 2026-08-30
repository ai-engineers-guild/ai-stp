"""Canonical public URLs for SEO subjects. Version/query routes are not canonical."""

from __future__ import annotations

from urllib.parse import quote

from ai_stp_contracts.seo import SeoSubjectKind


def origin_root(origin: str) -> str:
    return origin.rstrip("/")


def human_path(kind: SeoSubjectKind, subject_id: str, locale: str) -> str:
    if kind == "component":
        return f"/{locale}/catalog/components/{quote(subject_id)}"
    if kind == "setup":
        return f"/{locale}/catalog/setups/{quote(subject_id)}"
    if kind == "article":
        type_name, _, slug = subject_id.partition(":")
        return f"/{locale}/content/{quote(type_name)}/{quote(slug)}"
    if kind == "service":
        return f"/{locale}/services/{quote(subject_id)}"
    return f"/{locale}/countries/{quote(subject_id)}"


def canonical_url(origin: str, kind: SeoSubjectKind, subject_id: str, locale: str) -> str:
    return origin_root(origin) + human_path(kind, subject_id, locale)


def og_url(origin: str, revision_id: str) -> str:
    return f"{origin_root(origin)}/og/{revision_id}.png"


def markdown_url(origin: str, kind: SeoSubjectKind, subject_id: str) -> str:
    encoded = "/".join(quote(part) for part in subject_id.split("/"))
    return f"{origin_root(origin)}/llms/{kind}/{encoded}.md"


def shard_name(kind: SeoSubjectKind, locale: str, page: int) -> str:
    return f"{kind}-{locale}-{page}"


def sitemap_shard_url(origin: str, kind: SeoSubjectKind, locale: str, page: int) -> str:
    return f"{origin_root(origin)}/sitemaps/{shard_name(kind, locale, page)}.xml"
