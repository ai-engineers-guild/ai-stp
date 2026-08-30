"""Idempotent SEO effect for an activated ArticleRevision (SPEC-054 REQ-5412)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.seo.enqueue import enqueue_seo_build


async def enqueue_article_seo_effect(
    session: AsyncSession,
    *,
    article_id: str,
    locales: Sequence[str],
    source_digest: str,
) -> None:
    """Queue one seo_build job per locale. Duplicate keys are a no-op.

    The job is written in the caller's article transaction. A later SEO worker
    failure cannot roll back the article mutation.
    """
    await enqueue_seo_build(
        session,
        kind="article",
        subject_id=article_id,
        locales=locales,
        source_digest=source_digest,
    )
