"""Deterministic SEO base revision. Never waits on a model."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.seo import SEO_LOCALES
from ai_stp_platform.seo.collectors import SubjectMissing
from ai_stp_platform.seo.facts import parse_locale, parse_subject_kind
from ai_stp_platform.seo.materialize import (
    activate_base_revision,
    deactivate_subject,
    maybe_enqueue_enrichment,
)
from ai_stp_platform.seo.orm import SeoFactSnapshot
from ai_stp_platform.seo.settings import SeoSettings, load_seo_settings


async def handle_seo_build(
    session: AsyncSession,
    payload: Mapping[str, object],
    *,
    settings: SeoSettings | None = None,
    now: datetime | None = None,
) -> None:
    """Build and activate the base revision, then optionally enqueue enrichment."""
    kind = parse_subject_kind(payload.get("subject_kind"))
    subject_id = payload.get("subject_id")
    locale = parse_locale(payload.get("locale"))
    if not isinstance(subject_id, str) or not subject_id:
        raise ValueError("seo_build requires subject_id")
    if locale not in SEO_LOCALES:
        raise ValueError("seo_build requires locale")
    resolved = settings or load_seo_settings()
    moment = now or datetime.now(UTC)
    try:
        revision = await activate_base_revision(
            session,
            kind=kind,
            subject_id=subject_id,
            locale=locale,
            settings=resolved,
            now=moment,
        )
    except SubjectMissing:
        await deactivate_subject(
            session, kind=kind, subject_id=subject_id, locale=locale, now=moment
        )
        return
    snapshot = await session.get(SeoFactSnapshot, revision.snapshot_id)
    if snapshot is None:
        return
    await maybe_enqueue_enrichment(session, revision=revision, snapshot=snapshot, settings=resolved)
