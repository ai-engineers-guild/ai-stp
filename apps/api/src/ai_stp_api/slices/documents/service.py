"""Public documents and policies (SPEC-031)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_contracts.safe_markdown import render_description, source_digest
from ai_stp_platform.models import DocumentRevision, PublicDocument

KIND_BY_SLUG = {
    "privacy": "privacy",
    "cookies": "cookies",
    "service-rules": "service_rules",
    "licensing": "author_content_and_license",
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


async def ensure_document(db: AsyncSession, *, slug: str, kind: str) -> PublicDocument:
    result = await db.execute(select(PublicDocument).where(PublicDocument.slug == slug))
    row = result.scalar_one_or_none()
    if row is not None:
        return row
    row = PublicDocument(id=_new_id("doc"), slug=slug, kind=kind)
    db.add(row)
    await db.flush()
    return row


async def publish_revision(
    db: AsyncSession,
    *,
    slug: str,
    kind: str,
    locale: str,
    title: str,
    markdown_source: str,
    source_ref: str | None = None,
    source_path: str | None = None,
) -> dict[str, Any]:
    rendered = render_description(markdown_source)
    doc = await ensure_document(db, slug=slug, kind=kind)
    # Supersede previous published for locale.
    existing = await db.execute(
        select(DocumentRevision).where(
            DocumentRevision.document_id == doc.id,
            DocumentRevision.locale == locale,
            DocumentRevision.lifecycle == "published",
        )
    )
    for old in existing.scalars().all():
        old.lifecycle = "superseded"
    rev = DocumentRevision(
        id=_new_id("drev"),
        document_id=doc.id,
        locale=locale,
        lifecycle="published",
        title=title,
        markdown_source=markdown_source,
        content_digest=source_digest(markdown_source),
        renderer_version=rendered.renderer_version,
        source_type="repository" if source_ref else "staff",
        source_ref=source_ref,
        source_path=source_path,
        published_at=datetime.now(UTC),
    )
    db.add(rev)
    await db.flush()
    return _revision_public(doc, rev, rendered.html)


def _revision_public(doc: PublicDocument, rev: DocumentRevision, html: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "slug": doc.slug,
        "kind": doc.kind,
        "locale": rev.locale,
        "title": rev.title,
        "lifecycle": rev.lifecycle,
        "content_digest": rev.content_digest,
        "renderer_version": rev.renderer_version,
        "source_ref": rev.source_ref,
        "source_path": rev.source_path,
        "published_at": rev.published_at.isoformat().replace("+00:00", "Z")
        if rev.published_at
        else None,
        "html": html,
        "markdown_source": rev.markdown_source,
    }


async def get_published(
    db: AsyncSession,
    *,
    slug: str,
    locale: str,
    fallback_locale: str = "en",
) -> dict[str, Any]:
    result = await db.execute(select(PublicDocument).where(PublicDocument.slug == slug))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "not found")
    for loc in (locale, fallback_locale):
        rev_result = await db.execute(
            select(DocumentRevision)
            .where(
                DocumentRevision.document_id == doc.id,
                DocumentRevision.locale == loc,
                DocumentRevision.lifecycle == "published",
            )
            .order_by(DocumentRevision.published_at.desc())
            .limit(1)
        )
        rev = rev_result.scalar_one_or_none()
        if rev is not None:
            html = render_description(rev.markdown_source).html
            return _revision_public(doc, rev, html)
    raise ApiError(ErrorCategory.NOT_FOUND, "not found")
