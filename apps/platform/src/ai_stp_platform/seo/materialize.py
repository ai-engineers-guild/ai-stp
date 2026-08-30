"""Persist and activate SEO snapshots and revisions atomically."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.seo import (
    SEO_PROMPT_VERSION,
    SeoEnrichmentOutput,
    SeoProfileDocument,
    SeoSubjectKind,
)
from ai_stp_foundation.revisions import revision_id
from ai_stp_platform.seo.builder import apply_source_digest, build_base_profile, profile_digest
from ai_stp_platform.seo.collectors import SubjectMissing, collect_subject
from ai_stp_platform.seo.enqueue import enqueue_seo_enrich, job_payload_is_safe
from ai_stp_platform.seo.enrich import merge_enrichment
from ai_stp_platform.seo.facts import (
    PublicSubjectFacts,
    as_object_map,
    collect_public_facts,
    parse_subject_kind,
    snapshot_digest,
    snapshot_payload,
)
from ai_stp_platform.seo.metrics import record_seo_build
from ai_stp_platform.seo.orm import SeoActiveRevision, SeoFactSnapshot, SeoGeneration, SeoRevision
from ai_stp_platform.seo.settings import SeoSettings, load_seo_settings
from ai_stp_platform.seo.urls import og_url


def _now() -> datetime:
    return datetime.now(UTC)


async def _bump_generation(session: AsyncSession, now: datetime) -> int:
    await session.execute(
        pg_insert(SeoGeneration)
        .values(id=1, value=0, updated_at=now)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    await session.execute(
        update(SeoGeneration)
        .where(SeoGeneration.id == 1)
        .values(value=SeoGeneration.value + 1, updated_at=now)
    )
    value = await session.scalar(select(SeoGeneration.value).where(SeoGeneration.id == 1))
    return int(value or 0)


def _revision_identity(
    snapshot_id: str,
    *,
    generator_kind: str,
    template_version: str,
    prompt_version: str,
    model_alias: str,
) -> str:
    return revision_id(
        {
            "snapshot_id": snapshot_id,
            "generator_kind": generator_kind,
            "template_version": template_version,
            "prompt_version": prompt_version,
            "model_alias": model_alias,
        }
    )


async def existing_locale_urls(
    session: AsyncSession,
    *,
    kind: SeoSubjectKind,
    subject_id: str,
    origin: str,
) -> dict[str, str]:
    from ai_stp_platform.seo.urls import canonical_url

    rows = list(
        (
            await session.execute(
                select(SeoActiveRevision.locale).where(
                    SeoActiveRevision.subject_kind == kind,
                    SeoActiveRevision.subject_id == subject_id,
                )
            )
        ).scalars()
    )
    return {locale: canonical_url(origin, kind, subject_id, locale) for locale in rows}


async def persist_snapshot(
    session: AsyncSession, facts: PublicSubjectFacts, now: datetime
) -> SeoFactSnapshot:
    collect_public_facts(facts)
    digest = snapshot_digest(facts)
    payload = snapshot_payload(facts)
    existing = await session.get(SeoFactSnapshot, digest)
    if existing is not None:
        return existing
    row = SeoFactSnapshot(
        id=digest,
        subject_kind=facts.kind,
        subject_id=facts.subject_id,
        source_revision=facts.source_revision,
        locale=facts.locale,
        source_digest=digest,
        schema_version=1,
        facts=payload,
        captured_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def persist_revision(
    session: AsyncSession,
    *,
    snapshot: SeoFactSnapshot,
    profile: SeoProfileDocument,
    generator_kind: str,
    template_version: str,
    prompt_version: str,
    model_alias: str,
    state: str,
    now: datetime,
    error_code: str | None = None,
) -> SeoRevision:
    identity = _revision_identity(
        snapshot.id,
        generator_kind=generator_kind,
        template_version=template_version,
        prompt_version=prompt_version,
        model_alias=model_alias,
    )
    existing = await session.get(SeoRevision, identity)
    if existing is not None:
        return existing
    row = SeoRevision(
        id=identity,
        snapshot_id=snapshot.id,
        state=state,
        profile=cast(dict[str, object], profile.model_dump(mode="json")),
        profile_digest=profile_digest(profile),
        template_version=template_version,
        prompt_version=prompt_version,
        generator_kind=generator_kind,
        model_alias=model_alias,
        error_code=error_code,
        created_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def activate_revision(
    session: AsyncSession,
    *,
    revision: SeoRevision,
    snapshot: SeoFactSnapshot,
    now: datetime,
) -> int:
    generation = await _bump_generation(session, now)
    pointer = await session.scalar(
        select(SeoActiveRevision)
        .where(
            SeoActiveRevision.subject_kind == snapshot.subject_kind,
            SeoActiveRevision.subject_id == snapshot.subject_id,
            SeoActiveRevision.locale == snapshot.locale,
        )
        .with_for_update()
    )
    decision = as_object_map(revision.profile.get("index_decision"))
    eligible = False if decision is None else bool(decision.get("eligible"))
    previous_id = pointer.revision_id if pointer is not None else None
    if pointer is None:
        session.add(
            SeoActiveRevision(
                subject_kind=snapshot.subject_kind,
                subject_id=snapshot.subject_id,
                locale=snapshot.locale,
                revision_id=revision.id,
                snapshot_id=snapshot.id,
                generation=generation,
                index_eligible=eligible,
                updated_at=now,
            )
        )
    else:
        pointer.revision_id = revision.id
        pointer.snapshot_id = snapshot.id
        pointer.generation = generation
        pointer.index_eligible = eligible
        pointer.updated_at = now
    if previous_id and previous_id != revision.id:
        previous = await session.get(SeoRevision, previous_id)
        if previous is not None and previous.state == "active":
            previous.state = "base_ready" if previous.generator_kind == "template" else "rejected"
    revision.state = "active"
    revision.activated_at = now
    await session.flush()
    return generation


async def activate_base_revision(
    session: AsyncSession,
    *,
    kind: SeoSubjectKind,
    subject_id: str,
    locale: str,
    settings: SeoSettings | None = None,
    now: datetime | None = None,
    facts: PublicSubjectFacts | None = None,
) -> SeoRevision:
    """Build and activate the deterministic base revision. Never waits on a model."""
    moment = now or _now()
    started = moment
    resolved = settings or load_seo_settings()
    subject_facts = facts or await collect_subject(
        session, kind=kind, subject_id=subject_id, locale=locale
    )
    snapshot = await persist_snapshot(session, subject_facts, moment)
    locales = await existing_locale_urls(
        session, kind=kind, subject_id=subject_id, origin=resolved.public_origin
    )
    identity = _revision_identity(
        snapshot.id,
        generator_kind="template",
        template_version=resolved.template_version,
        prompt_version="",
        model_alias="",
    )
    existing = await session.get(SeoRevision, identity)
    pointer = await session.scalar(
        select(SeoActiveRevision).where(
            SeoActiveRevision.subject_kind == kind,
            SeoActiveRevision.subject_id == subject_id,
            SeoActiveRevision.locale == locale,
        )
    )
    if existing is not None and pointer is not None and pointer.revision_id == existing.id:
        record_seo_build(outcome="idempotent", duration_ms=0, index_reasons=[])
        return existing
    profile = build_base_profile(
        subject_facts,
        origin=resolved.public_origin,
        revision_id=identity,
        source_digest=snapshot.source_digest,
        existing_locales=locales,
        template_version=resolved.template_version,
    )
    profile = apply_source_digest(profile, snapshot.source_digest)
    revision = await persist_revision(
        session,
        snapshot=snapshot,
        profile=profile,
        generator_kind="template",
        template_version=resolved.template_version,
        prompt_version="",
        model_alias="",
        state="base_ready",
        now=moment,
    )
    await activate_revision(session, revision=revision, snapshot=snapshot, now=moment)
    duration_ms = int(((_now() if now is None else moment) - started).total_seconds() * 1000)
    reasons = list(profile.index_decision.reasons)
    record_seo_build(outcome="base_active", duration_ms=max(duration_ms, 0), index_reasons=reasons)
    return revision


async def rollback_to_base(
    session: AsyncSession,
    *,
    kind: SeoSubjectKind,
    subject_id: str,
    locale: str,
    now: datetime | None = None,
) -> SeoRevision:
    """Point the subject at the last valid template revision. Domain object stays."""
    moment = now or _now()
    pointer = await session.scalar(
        select(SeoActiveRevision)
        .where(
            SeoActiveRevision.subject_kind == kind,
            SeoActiveRevision.subject_id == subject_id,
            SeoActiveRevision.locale == locale,
        )
        .with_for_update()
    )
    if pointer is None:
        raise SubjectMissing(subject_id)
    base = await session.scalar(
        select(SeoRevision)
        .where(
            SeoRevision.snapshot_id == pointer.snapshot_id,
            SeoRevision.generator_kind == "template",
            SeoRevision.state.in_(("base_ready", "active")),
        )
        .order_by(SeoRevision.created_at.desc())
    )
    if base is None:
        raise SubjectMissing(subject_id)
    snapshot = await session.get(SeoFactSnapshot, pointer.snapshot_id)
    if snapshot is None:
        raise SubjectMissing(subject_id)
    await activate_revision(session, revision=base, snapshot=snapshot, now=moment)
    return base


async def deactivate_subject(
    session: AsyncSession,
    *,
    kind: SeoSubjectKind,
    subject_id: str,
    locale: str,
    now: datetime | None = None,
) -> None:
    """Drop the serving pointer without deleting revision history."""
    moment = now or _now()
    pointer = await session.scalar(
        select(SeoActiveRevision)
        .where(
            SeoActiveRevision.subject_kind == kind,
            SeoActiveRevision.subject_id == subject_id,
            SeoActiveRevision.locale == locale,
        )
        .with_for_update()
    )
    if pointer is None:
        return
    await session.delete(pointer)
    await _bump_generation(session, moment)
    await session.flush()


async def apply_enrichment(
    session: AsyncSession,
    *,
    snapshot: SeoFactSnapshot,
    base: SeoProfileDocument,
    output: SeoEnrichmentOutput,
    settings: SeoSettings,
    now: datetime | None = None,
) -> SeoRevision:
    """Persist an accepted model revision and activate it atomically."""
    moment = now or _now()
    identity = _revision_identity(
        snapshot.id,
        generator_kind="model",
        template_version=settings.template_version,
        prompt_version=settings.prompt_version or SEO_PROMPT_VERSION,
        model_alias=settings.enrichment_model_alias,
    )
    existing = await session.get(SeoRevision, identity)
    if existing is not None:
        if existing.state == "active":
            return existing
        if existing.state in {"rejected", "stale", "failed"}:
            return existing
        await activate_revision(session, revision=existing, snapshot=snapshot, now=moment)
        return existing
    merged = merge_enrichment(base, output)
    generator = merged.generator.model_copy(
        update={
            "template_version": settings.template_version,
            "prompt_version": settings.prompt_version or SEO_PROMPT_VERSION,
            "model_alias": settings.enrichment_model_alias,
        }
    )
    social = merged.social.model_copy(
        update={"image_url": og_url(settings.public_origin, identity)}
    )
    merged = merged.model_copy(update={"social": social, "generator": generator})
    merged = apply_source_digest(merged, snapshot.source_digest)
    revision = await persist_revision(
        session,
        snapshot=snapshot,
        profile=merged,
        generator_kind="model",
        template_version=settings.template_version,
        prompt_version=settings.prompt_version or SEO_PROMPT_VERSION,
        model_alias=settings.enrichment_model_alias,
        state="validating",
        now=moment,
    )
    await activate_revision(session, revision=revision, snapshot=snapshot, now=moment)
    return revision


async def persist_rejected(
    session: AsyncSession,
    *,
    snapshot: SeoFactSnapshot,
    base: SeoProfileDocument,
    settings: SeoSettings,
    state: str,
    error_code: str,
    now: datetime | None = None,
) -> SeoRevision:
    moment = now or _now()
    return await persist_revision(
        session,
        snapshot=snapshot,
        profile=base,
        generator_kind="model",
        template_version=settings.template_version,
        prompt_version=settings.prompt_version or SEO_PROMPT_VERSION,
        model_alias=settings.enrichment_model_alias,
        state=state,
        now=moment,
        error_code=error_code,
    )


async def maybe_enqueue_enrichment(
    session: AsyncSession,
    *,
    revision: SeoRevision,
    snapshot: SeoFactSnapshot,
    settings: SeoSettings,
) -> None:
    del revision
    if not settings.enrichment_enabled:
        return
    payload = {
        "subject_kind": snapshot.subject_kind,
        "subject_id": snapshot.subject_id,
        "locale": snapshot.locale,
        "snapshot_id": snapshot.id,
        "source_digest": snapshot.source_digest,
        "template_version": settings.template_version,
        "prompt_version": settings.prompt_version or SEO_PROMPT_VERSION,
        "model_alias": settings.enrichment_model_alias,
    }
    if not job_payload_is_safe(payload):
        return
    await enqueue_seo_enrich(
        session,
        kind=parse_subject_kind(snapshot.subject_kind),
        subject_id=snapshot.subject_id,
        locale=snapshot.locale,
        snapshot_id=snapshot.id,
        source_digest=snapshot.source_digest,
        template_version=settings.template_version,
        prompt_version=settings.prompt_version or SEO_PROMPT_VERSION,
        model_alias=settings.enrichment_model_alias,
    )
