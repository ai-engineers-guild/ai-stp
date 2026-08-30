"""Deterministic base SEO profile builder. No network and no model."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from ai_stp_contracts.safe_markdown import excerpt_from_source, validate_description
from ai_stp_contracts.seo import (
    SEO_OG_HEIGHT,
    SEO_OG_WIDTH,
    SEO_PROFILE_DOMAIN,
    SEO_TEMPLATE_VERSION,
    SeoGenerator,
    SeoIndexDecision,
    SeoLink,
    SeoProfileDocument,
    SeoSection,
    SeoSocial,
    SeoSubjectKind,
    SeoSubjectRef,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.seo.facts import (
    PublicSubjectFacts,
    as_object_map,
    extras_list,
    extras_text,
    mapping_text,
)
from ai_stp_platform.seo.index_decision import decide_index
from ai_stp_platform.seo.urls import canonical_url, og_url

_KIND_LABEL = {
    "en": {
        "component": "component",
        "setup": "setup",
        "article": "article",
        "service": "service",
        "country": "country",
        "catalog": "Catalog",
        "home": "Home",
        "content": "Content",
        "services": "Services",
        "countries": "Countries",
        "purpose": "Purpose",
        "compatibility": "Compatibility",
        "requirements": "Requirements",
        "permissions": "Permissions",
        "credentials": "Credentials",
        "verification": "Verification",
        "source": "Source",
        "author": "Author",
        "versions": "Versions",
        "related": "Related",
        "body": "Article",
        "objects": "Related objects",
        "site": "ai_stp",
    },
    "ru": {
        "component": "компонент",
        "setup": "сетап",
        "article": "статья",
        "service": "сервис",
        "country": "страна",
        "catalog": "Каталог",
        "home": "Главная",
        "content": "Материалы",
        "services": "Сервисы",
        "countries": "Страны",
        "purpose": "Назначение",
        "compatibility": "Совместимость",
        "requirements": "Требования",
        "permissions": "Полномочия",
        "credentials": "Учётные данные",
        "verification": "Проверка",
        "source": "Источник",
        "author": "Автор",
        "versions": "Версии",
        "related": "Связанное",
        "body": "Статья",
        "objects": "Связанные объекты",
        "site": "ai_stp",
    },
}


def _clip(text: str, limit: int) -> str:
    stripped = " ".join(text.split())
    if not stripped:
        stripped = "ai_stp"
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1].rstrip() + "…"


def _label(locale: str, key: str) -> str:
    table = _KIND_LABEL["ru" if locale == "ru" else "en"]
    return table[key]


def _safe_summary(text: str) -> str:
    try:
        return validate_description(text)
    except ValueError:
        return excerpt_from_source(text) or "ai_stp"


def _breadcrumb(origin: str, locale: str, facts: PublicSubjectFacts) -> list[SeoLink]:
    home = canonical_url(origin, "component", "unused", locale).rsplit("/catalog/", 1)[0]
    # Home is the locale root, not a fake component.
    home_url = origin.rstrip("/") + f"/{locale}"
    crumbs = [
        SeoLink(rel="home", href=home_url, text=_label(locale, "home")),
    ]
    del home
    if facts.kind in {"component", "setup"}:
        crumbs.append(
            SeoLink(
                rel="catalog",
                href=origin.rstrip("/") + f"/{locale}/catalog",
                text=_label(locale, "catalog"),
            )
        )
    elif facts.kind == "article":
        crumbs.append(
            SeoLink(
                rel="content",
                href=origin.rstrip("/") + f"/{locale}/content",
                text=_label(locale, "content"),
            )
        )
    elif facts.kind == "service":
        crumbs.append(
            SeoLink(
                rel="services",
                href=origin.rstrip("/") + f"/{locale}/services",
                text=_label(locale, "services"),
            )
        )
    elif facts.kind == "country":
        crumbs.append(
            SeoLink(
                rel="countries",
                href=origin.rstrip("/") + f"/{locale}/countries",
                text=_label(locale, "countries"),
            )
        )
    crumbs.append(
        SeoLink(
            rel="self",
            href=canonical_url(origin, facts.kind, facts.subject_id, locale),
            text=_clip(facts.name or facts.subject_id, 200),
            kind=facts.kind,
            subject_id=facts.subject_id,
        )
    )
    return crumbs


def _internal_links(origin: str, locale: str, facts: PublicSubjectFacts) -> list[SeoLink]:
    links: list[SeoLink] = []
    seen: set[str] = set()

    def add(kind: SeoSubjectKind, subject_id: str, text: str, rel: str) -> None:
        key = f"{kind}:{subject_id}"
        if key in seen or not subject_id:
            return
        seen.add(key)
        links.append(
            SeoLink(
                rel=rel,
                href=canonical_url(origin, kind, subject_id, locale),
                text=_clip(text or subject_id, 200),
                kind=kind,
                subject_id=subject_id,
            )
        )

    for item in extras_list(facts.extras, "related_components"):
        mapping = as_object_map(item)
        if mapping is not None:
            add(
                "component",
                mapping_text(mapping, "stable_id"),
                mapping_text(mapping, "name"),
                "related",
            )
    for item in extras_list(facts.extras, "related_setups"):
        mapping = as_object_map(item)
        if mapping is not None:
            add(
                "setup",
                mapping_text(mapping, "stable_id"),
                mapping_text(mapping, "name"),
                "related",
            )
    for item in extras_list(facts.extras, "services"):
        mapping = as_object_map(item)
        if mapping is not None:
            add(
                "service",
                mapping_text(mapping, "canonical_domain") or mapping_text(mapping, "domain"),
                mapping_text(mapping, "name"),
                "service",
            )
        elif isinstance(item, str):
            add("service", item, item, "service")
    for item in extras_list(facts.extras, "countries"):
        if isinstance(item, str):
            add("country", item, item, "country")
    for item in extras_list(facts.extras, "objects"):
        mapping = as_object_map(item)
        if mapping is None:
            continue
        kind = mapping.get("object_kind")
        sid = mapping_text(mapping, "stable_id")
        if kind == "component":
            add("component", sid, mapping_text(mapping, "name") or sid, "object")
        elif kind == "setup":
            add("setup", sid, mapping_text(mapping, "name") or sid, "object")
    for item in extras_list(facts.extras, "related_articles"):
        mapping = as_object_map(item)
        if mapping is not None:
            add(
                "article",
                mapping_text(mapping, "article_id"),
                mapping_text(mapping, "title"),
                "related",
            )
    return links[:48]


def _named_item(item: object) -> str:
    mapping = as_object_map(item)
    if mapping is None:
        return str(item)
    return mapping_text(mapping, "name") or str(item)


def _version_item(item: object) -> str:
    mapping = as_object_map(item)
    if mapping is None:
        return str(item)
    return mapping_text(mapping, "version") or str(item)


def _section(section_id: str, heading: str, body: str) -> SeoSection | None:
    text = " ".join(str(body).split())
    if not text:
        return None
    return SeoSection(id=section_id, heading=_clip(heading, 200), body=_clip(text, 8000))


def _kind_sections(locale: str, facts: PublicSubjectFacts) -> list[SeoSection]:
    extras = facts.extras
    sections: list[SeoSection] = []
    purpose = extras_text(extras, "purpose", "description") or facts.description
    if facts.kind in {"component", "setup"}:
        for built in (
            _section("purpose", _label(locale, "purpose"), purpose),
            _section(
                "compatibility",
                _label(locale, "compatibility"),
                extras_text(extras, "compatibility")
                or " ".join(str(item) for item in extras_list(extras, "supported_os")),
            ),
            _section(
                "requirements",
                _label(locale, "requirements"),
                extras_text(extras, "requirements")
                or " ".join(
                    [
                        *(_named_item(item) for item in extras_list(extras, "required_env")),
                        *(str(item) for item in extras_list(extras, "runtime_requirements")),
                    ]
                ),
            ),
            _section(
                "permissions",
                _label(locale, "permissions"),
                extras_text(extras, "permissions"),
            ),
            _section(
                "credentials",
                _label(locale, "credentials"),
                "required" if extras.get("requires_credentials") else "none",
            ),
            _section(
                "verification",
                _label(locale, "verification"),
                extras_text(extras, "verification")
                or (
                    f"author_verified={bool(extras.get('author_verified'))} "
                    f"component_verified={bool(extras.get('component_verified'))}"
                ),
            ),
            _section("source", _label(locale, "source"), extras_text(extras, "source_repository")),
            _section("author", _label(locale, "author"), extras_text(extras, "author_name")),
            _section(
                "versions",
                _label(locale, "versions"),
                extras_text(extras, "versions_text")
                or " ".join(_version_item(item) for item in extras_list(extras, "versions")),
            ),
            _section("related", _label(locale, "related"), extras_text(extras, "relations_text")),
        ):
            if built is not None:
                sections.append(built)
    elif facts.kind == "article":
        for built in (
            _section("author", _label(locale, "author"), extras_text(extras, "author_name")),
            _section(
                "body", _label(locale, "body"), extras_text(extras, "body_excerpt") or facts.summary
            ),
            _section("related", _label(locale, "related"), extras_text(extras, "relations_text")),
        ):
            if built is not None:
                sections.append(built)
    else:
        for built in (
            _section("purpose", _label(locale, "purpose"), purpose),
            _section("objects", _label(locale, "objects"), extras_text(extras, "objects_text")),
            _section("related", _label(locale, "related"), extras_text(extras, "relations_text")),
        ):
            if built is not None:
                sections.append(built)
    if not sections:
        fallback = _section("purpose", _label(locale, "purpose"), facts.description or facts.name)
        if fallback is not None:
            sections.append(fallback)
    return sections


def _json_ld(
    *,
    origin: str,
    facts: PublicSubjectFacts,
    canonical: str,
    title: str,
    description: str,
    image: str,
    sections: Sequence[SeoSection],
    breadcrumbs: Sequence[SeoLink],
    decision: SeoIndexDecision,
) -> dict[str, object]:
    kind_type = {
        "component": "SoftwareSourceCode",
        "setup": "SoftwareApplication",
        "article": "TechArticle"
        if str(facts.extras.get("article_type")) == "article"
        else "Article",
        "service": "Service",
        "country": "CollectionPage",
    }[facts.kind]
    primary: dict[str, object] = {
        "@type": kind_type,
        "name": title,
        "description": description,
        "url": canonical,
        "mainEntityOfPage": canonical,
        "image": image,
        "inLanguage": facts.locale,
        "datePublished": format_timestamp(facts.published_at),
        "dateModified": format_timestamp(facts.modified_at),
    }
    if facts.tags:
        primary["keywords"] = ", ".join(facts.tags)
    if facts.kind == "article":
        primary["headline"] = title
        primary["articleSection"] = str(facts.extras.get("article_type") or "article")
    if facts.kind == "service":
        primary["serviceType"] = "AI agent integration"
        countries = [str(item) for item in extras_list(facts.extras, "countries")]
        if countries:
            primary["areaServed"] = countries
        same_as = extras_text(facts.extras, "primary_url", "source_url")
        if same_as:
            primary["sameAs"] = same_as
    if facts.kind == "component":
        for key, value in (
            ("codeRepository", extras_text(facts.extras, "source_repository")),
            ("runtimePlatform", extras_text(facts.extras, "harness_id")),
            ("version", extras_text(facts.extras, "version")),
        ):
            if value:
                primary[key] = value
        license_data = as_object_map(facts.extras.get("license"))
        if license_data is not None and mapping_text(license_data, "spdx_id"):
            primary["license"] = mapping_text(license_data, "spdx_id")
    graph: list[dict[str, object]] = [
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": index, "name": crumb.text, "item": crumb.href}
                for index, crumb in enumerate(breadcrumbs, start=1)
            ],
        },
        primary,
    ]
    author = extras_text(facts.extras, "author_name")
    if author:
        author_id = f"{canonical}#author"
        primary["author"] = {"@id": author_id}
        graph.append({"@type": "Person", "@id": author_id, "name": author})
    visible_ids = {section.id for section in sections}
    # Structured data repeats only visible section facts. Hidden FAQ/rating/price stay out.
    del visible_ids, decision, origin
    return {"@context": "https://schema.org", "@graph": graph}


def build_base_profile(
    facts: PublicSubjectFacts,
    *,
    origin: str,
    revision_id: str,
    source_digest: str,
    existing_locales: Mapping[str, str] | None = None,
    template_version: str = SEO_TEMPLATE_VERSION,
) -> SeoProfileDocument:
    """Build a complete base profile from public facts. Never calls a model."""
    decision = decide_index(facts)
    canonical = canonical_url(origin, facts.kind, facts.subject_id, facts.locale)
    kind_label = _label(facts.locale, facts.kind)
    heading = _clip(facts.name or facts.subject_id, 200)
    title = _clip(f"{heading} — {kind_label}", 160)
    description = _clip(facts.description or facts.summary or heading, 320)
    summary = _safe_summary(facts.summary or facts.description or heading)
    tags = list(dict.fromkeys(tag for tag in facts.tags if tag))[:12]
    locales = dict(existing_locales or {})
    locales[facts.locale] = canonical
    breadcrumbs = _breadcrumb(origin, facts.locale, facts)
    sections = _kind_sections(facts.locale, facts)
    links = _internal_links(origin, facts.locale, facts)
    image = og_url(origin, revision_id)
    social = SeoSocial(
        title=title,
        description=description,
        image_url=image,
        image_alt=_clip(f"{title} ({SEO_OG_WIDTH}x{SEO_OG_HEIGHT})", 200),
        locale=facts.locale,
    )
    json_ld = _json_ld(
        origin=origin,
        facts=facts,
        canonical=canonical,
        title=title,
        description=description,
        image=image,
        sections=sections,
        breadcrumbs=breadcrumbs,
        decision=decision,
    )
    return SeoProfileDocument(
        subject=SeoSubjectRef(
            kind=facts.kind,
            id=facts.subject_id,
            source_revision=facts.source_revision,
            source_digest=source_digest,
        ),
        locale=facts.locale,
        canonical_url=canonical,
        title=title,
        description=description,
        heading=heading,
        summary=summary,
        taxonomy_tags=tags,
        search_intents=tags[:12],
        alternates=locales,
        robots="index,follow" if decision.eligible else "noindex,follow",
        index_decision=decision,
        breadcrumbs=breadcrumbs,
        sections=sections,
        internal_links=links,
        json_ld=json_ld,
        social=social,
        published_at=format_timestamp(facts.published_at),
        modified_at=format_timestamp(facts.modified_at),
        generator=SeoGenerator(kind="template", template_version=template_version),
    )


def profile_digest(profile: SeoProfileDocument) -> str:
    return digest_canonical(SEO_PROFILE_DOMAIN, cast(JsonValue, profile.model_dump(mode="json")))


def apply_source_digest(profile: SeoProfileDocument, digest: str) -> SeoProfileDocument:
    subject = profile.subject.model_copy(update={"source_digest": digest})
    return profile.model_copy(update={"subject": subject})
