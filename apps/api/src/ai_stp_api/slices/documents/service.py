"""Public immutable documents and bundled legal-policy publication."""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_contracts.safe_markdown import render_description
from ai_stp_platform.legal.builtin import builtin_policies
from ai_stp_platform.models import DocumentRevision, PublicDocument

KIND_BY_SLUG = {
    "privacy": "privacy",
    "cookies": "cookies",
    "service-rules": "service_rules",
    "licensing": "author_content_and_license",
    "personal-data-consent": "personal_data_consent",
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


async def ensure_document(db: AsyncSession, *, slug: str, kind: str) -> PublicDocument:
    row = await db.scalar(select(PublicDocument).where(PublicDocument.slug == slug))
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
    policy_version: str = "1.0",
    effective_at: date | None = None,
    source_type: str | None = None,
    source_ref: str | None = None,
    source_path: str | None = None,
) -> dict[str, Any]:
    """Publish one source digest once; old revisions remain addressable."""
    rendered = render_description(markdown_source)
    doc = await ensure_document(db, slug=slug, kind=kind)
    identical = await db.scalar(
        select(DocumentRevision).where(
            DocumentRevision.document_id == doc.id,
            DocumentRevision.locale == locale,
            DocumentRevision.content_digest == rendered.source_digest,
        )
    )
    if identical is not None:
        return _revision_public(doc, identical, render_description(identical.markdown_source).html)

    previous = (
        (
            await db.execute(
                select(DocumentRevision).where(
                    DocumentRevision.document_id == doc.id,
                    DocumentRevision.locale == locale,
                    DocumentRevision.lifecycle == "published",
                )
            )
        )
        .scalars()
        .all()
    )
    for old in previous:
        old.lifecycle = "superseded"
    revision = DocumentRevision(
        id=_new_id("drev"),
        document_id=doc.id,
        locale=locale,
        lifecycle="published",
        title=title,
        policy_version=policy_version,
        effective_at=datetime.combine(effective_at, time.min, UTC) if effective_at else None,
        markdown_source=markdown_source,
        content_digest=rendered.source_digest,
        renderer_version=rendered.renderer_version,
        source_type=source_type or ("repository" if source_ref else "staff"),
        source_ref=source_ref,
        source_path=source_path,
        published_at=datetime.now(UTC),
        supersedes_id=previous[0].id if previous else None,
    )
    db.add(revision)
    await db.flush()
    return _revision_public(doc, revision, rendered.html)


def _revision_public(doc: PublicDocument, rev: DocumentRevision, html: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "slug": doc.slug,
        "kind": doc.kind,
        "revision_id": rev.id,
        "locale": rev.locale,
        "title": rev.title,
        "policy_version": rev.policy_version,
        "effective_at": rev.effective_at.isoformat().replace("+00:00", "Z")
        if rev.effective_at
        else None,
        "lifecycle": rev.lifecycle,
        "content_digest": rev.content_digest,
        "renderer_version": rev.renderer_version,
        "source_ref": rev.source_ref,
        "source_path": rev.source_path,
        "supersedes_id": rev.supersedes_id,
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
    revision_id: str | None = None,
) -> dict[str, Any]:
    doc = await db.scalar(select(PublicDocument).where(PublicDocument.slug == slug))
    if doc is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "not found")
    if revision_id is not None:
        revision = await db.scalar(
            select(DocumentRevision).where(
                DocumentRevision.id == revision_id,
                DocumentRevision.document_id == doc.id,
                DocumentRevision.lifecycle.in_(("published", "superseded")),
            )
        )
        if revision is None:
            raise ApiError(ErrorCategory.NOT_FOUND, "not found")
        return _revision_public(doc, revision, render_description(revision.markdown_source).html)
    for loc in (locale, fallback_locale):
        revision = await db.scalar(
            select(DocumentRevision)
            .where(
                DocumentRevision.document_id == doc.id,
                DocumentRevision.locale == loc,
                DocumentRevision.lifecycle == "published",
            )
            .order_by(DocumentRevision.published_at.desc())
            .limit(1)
        )
        if revision is not None:
            return _revision_public(
                doc, revision, render_description(revision.markdown_source).html
            )
    raise ApiError(ErrorCategory.NOT_FOUND, "not found")


async def current_published_revision(
    db: AsyncSession, *, slug: str, locale: str = "en"
) -> DocumentRevision:
    """Return the exact current revision needed by legal onboarding."""
    doc = await db.scalar(select(PublicDocument).where(PublicDocument.slug == slug))
    if doc is None:
        raise ApiError(ErrorCategory.DEPENDENCY, "required legal policy is unavailable")
    for loc in (locale, "en"):
        revision = await db.scalar(
            select(DocumentRevision)
            .where(
                DocumentRevision.document_id == doc.id,
                DocumentRevision.locale == loc,
                DocumentRevision.lifecycle == "published",
            )
            .order_by(DocumentRevision.published_at.desc())
            .limit(1)
        )
        if revision is not None:
            return revision
    raise ApiError(ErrorCategory.DEPENDENCY, "required legal policy is unavailable")


async def sync_builtin_policies(
    db: AsyncSession,
    *,
    source_ref: str | None,
) -> None:
    """Synchronize reviewed packaged Markdown into immutable document revisions."""
    for policy in builtin_policies():
        await publish_revision(
            db,
            slug=policy.slug,
            kind=policy.kind,
            locale=policy.locale,
            title=policy.title,
            markdown_source=policy.markdown_source,
            policy_version=policy.policy_version,
            effective_at=policy.effective_at,
            source_type="repository",
            source_ref=source_ref,
            source_path=policy.source_path,
        )
