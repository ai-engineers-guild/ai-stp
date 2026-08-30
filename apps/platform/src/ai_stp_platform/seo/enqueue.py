"""Transactional SEO job placement. Duplicate coordinates are a no-op."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.seo import (
    SEO_LOCALES,
    SEO_TEMPLATE_VERSION,
    SeoSubjectKind,
)
from ai_stp_platform.queue.engine import enqueue
from ai_stp_platform.queue.states import JobType
from ai_stp_platform.seo.facts import parse_locale, parse_subject_kind
from ai_stp_platform.seo.orm import SeoActiveRevision, SeoFactSnapshot, SeoRevision
from ai_stp_platform.seo.settings import SeoSettings, load_seo_settings

_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {"credential", "prompt", "artifact", "finding", "password", "token"}
)


def job_payload_is_safe(payload: dict[str, Any]) -> bool:
    """Reject secret-bearing field names. Values may contain those English words.

    A substring scan over values refused `article:immutable-artifacts` and any
    `prompt_version` enrich payload, so publication never reached the worker.
    """
    return not any(str(key).lower() in _FORBIDDEN_PAYLOAD_KEYS for key in payload)


def mutation_digest(*parts: str) -> str:
    """Stable job identity for one source mutation. Not a snapshot digest."""
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(part.encode("utf-8"))
        hasher.update(b"\0")
    return f"sha256:{hasher.hexdigest()}"


async def enqueue_seo_build(
    session: AsyncSession,
    *,
    kind: SeoSubjectKind,
    subject_id: str,
    locales: Iterable[str] = SEO_LOCALES,
    source_digest: str,
    template_version: str | None = None,
) -> None:
    """Enqueue one seo_build job per locale in the caller's transaction."""
    if not source_digest:
        raise ValueError("seo_build requires source_digest")
    version = template_version or load_seo_settings().template_version or SEO_TEMPLATE_VERSION
    for locale in locales:
        payload = {
            "subject_kind": kind,
            "subject_id": subject_id,
            "locale": locale,
            "source_digest": source_digest,
            "template_version": version,
        }
        if not job_payload_is_safe(payload):
            raise ValueError("seo_build payload is unsafe")
        key = f"seo-build:{kind}:{subject_id}:{locale}:{source_digest}:{version}"
        await enqueue(
            session,
            job_type=JobType.SEO_BUILD,
            payload=payload,
            idempotency_key=key,
        )


async def enqueue_seo_enrich(
    session: AsyncSession,
    *,
    kind: SeoSubjectKind,
    subject_id: str,
    locale: str,
    snapshot_id: str,
    source_digest: str,
    template_version: str,
    prompt_version: str,
    model_alias: str,
) -> None:
    payload = {
        "subject_kind": kind,
        "subject_id": subject_id,
        "locale": locale,
        "snapshot_id": snapshot_id,
        "source_digest": source_digest,
        "template_version": template_version,
        "prompt_version": prompt_version,
        "model_alias": model_alias,
    }
    if not job_payload_is_safe(payload):
        raise ValueError("seo_enrich payload is unsafe")
    await enqueue(
        session,
        job_type=JobType.SEO_ENRICH,
        payload=payload,
        idempotency_key=(
            f"seo-enrich:{kind}:{subject_id}:{locale}:{source_digest}:"
            f"{template_version}:{prompt_version}:{model_alias}"
        ),
    )


async def enqueue_refresh_for_active(
    session: AsyncSession,
    *,
    settings: SeoSettings | None = None,
) -> tuple[int, int]:
    """Rebuild stale templates; enrich only revisions already on the current template."""
    resolved = settings or load_seo_settings()
    rows = (
        await session.execute(
            select(SeoActiveRevision, SeoRevision).join(
                SeoRevision, SeoRevision.id == SeoActiveRevision.revision_id
            )
        )
    ).all()
    builds = enrichments = 0
    for pointer, revision in rows:
        snapshot = await session.get(SeoFactSnapshot, pointer.snapshot_id)
        if snapshot is None:
            continue
        kind = parse_subject_kind(pointer.subject_kind)
        locale = parse_locale(pointer.locale)
        if revision.template_version != resolved.template_version:
            await enqueue_seo_build(
                session,
                kind=kind,
                subject_id=pointer.subject_id,
                locales=(locale,),
                source_digest=snapshot.source_digest,
                template_version=resolved.template_version,
            )
            builds += 1
            continue
        if not resolved.enrichment_enabled or (
            revision.generator_kind == "model"
            and revision.prompt_version == resolved.prompt_version
            and revision.model_alias == resolved.enrichment_model_alias
        ):
            continue
        await enqueue_seo_enrich(
            session,
            kind=kind,
            subject_id=pointer.subject_id,
            locale=locale,
            snapshot_id=snapshot.id,
            source_digest=snapshot.source_digest,
            template_version=resolved.template_version,
            prompt_version=resolved.prompt_version,
            model_alias=resolved.enrichment_model_alias,
        )
        enrichments += 1
    return builds, enrichments


async def enqueue_service_and_countries(
    session: AsyncSession,
    *,
    domain: str,
    country_codes: Iterable[str],
    extra: str = "",
) -> None:
    codes = sorted(set(country_codes))
    digest = mutation_digest("service", domain, *codes, extra)
    await enqueue_seo_build(session, kind="service", subject_id=domain, source_digest=digest)
    for code in codes:
        await enqueue_seo_build(
            session,
            kind="country",
            subject_id=code.upper(),
            source_digest=digest,
        )
