"""Optional LiteLLM enrichment. Failures leave the base revision active."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from time import monotonic

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.seo import SEO_LOCALES, SeoEnrichmentOutput, SeoProfileDocument
from ai_stp_platform.logging import get_logger
from ai_stp_platform.seo.collectors import SubjectMissing, collect_subject
from ai_stp_platform.seo.enrich import (
    SeoEnrichmentRejected,
    content_from_response,
    current_source_digest,
    fetch_enrichment,
    request_body,
    usage_from_response,
    validate_enrichment_output,
)
from ai_stp_platform.seo.facts import parse_locale, parse_subject_kind, snapshot_digest
from ai_stp_platform.seo.materialize import apply_enrichment, persist_rejected
from ai_stp_platform.seo.metrics import record_seo_enrich
from ai_stp_platform.seo.orm import SeoFactSnapshot, SeoRevision
from ai_stp_platform.seo.settings import SeoSettings, load_seo_settings

FetchFn = Callable[..., Awaitable[dict[str, object]]]
MAX_ENRICHMENT_ATTEMPTS = 5
_log = get_logger("seo_enrich")


def _payload_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"seo_enrich requires {key}")
    return value


async def handle_seo_enrich(
    session: AsyncSession,
    payload: Mapping[str, object],
    *,
    settings: SeoSettings | None = None,
    fetch: FetchFn | None = None,
    now: datetime | None = None,
) -> None:
    """Call one configured LiteLLM URL. Routing to CLIPROXY is not in this handler."""
    resolved = settings or load_seo_settings()
    if not resolved.enrichment_enabled or not resolved.enrichment_url:
        return
    kind = parse_subject_kind(_payload_str(payload, "subject_kind"))
    subject_id = _payload_str(payload, "subject_id")
    locale = parse_locale(_payload_str(payload, "locale"))
    snapshot_id = _payload_str(payload, "snapshot_id")
    expected_digest = _payload_str(payload, "source_digest")
    template_version = _payload_str(payload, "template_version")
    if locale not in SEO_LOCALES:
        raise ValueError("seo_enrich requires locale")
    moment = now or datetime.now(UTC)
    started = monotonic()
    snapshot = await session.get(SeoFactSnapshot, snapshot_id)
    if snapshot is None:
        record_seo_enrich(
            outcome="stale",
            duration_ms=0,
            model_alias=resolved.enrichment_model_alias,
        )
        return
    try:
        current = await collect_subject(
            session,
            kind=kind,
            subject_id=subject_id,
            locale=locale,
        )
    except SubjectMissing:
        record_seo_enrich(
            outcome="stale",
            duration_ms=0,
            model_alias=resolved.enrichment_model_alias,
        )
        return
    if snapshot_digest(current) != snapshot.id or expected_digest != current_source_digest(
        snapshot
    ):
        base = _base_profile(session, snapshot, template_version=template_version)
        profile = await base
        await persist_rejected(
            session,
            snapshot=snapshot,
            base=profile,
            settings=resolved,
            state="stale",
            error_code="AI_STP_SEO_SOURCE_STALE",
            now=moment,
        )
        record_seo_enrich(
            outcome="stale",
            duration_ms=int((monotonic() - started) * 1000),
            model_alias=resolved.enrichment_model_alias,
        )
        return
    profile = await _base_profile(session, snapshot, template_version=template_version)
    try:
        feedback: str | None = None
        output: SeoEnrichmentOutput | None = None
        raw_response: dict[str, object] = {}
        for attempt in range(MAX_ENRICHMENT_ATTEMPTS):
            body = request_body(
                snapshot=dict(snapshot.facts),
                instruction_version=resolved.prompt_version,
                model_alias=resolved.enrichment_model_alias,
                feedback=feedback,
            )
            if fetch is not None:
                raw_response = await fetch(
                    url=resolved.enrichment_url,
                    credential=resolved.enrichment_credential,
                    body=body,
                    timeout_seconds=resolved.enrichment_timeout_seconds,
                )
            else:
                raw_response = await fetch_enrichment(
                    url=resolved.enrichment_url,
                    credential=resolved.enrichment_credential,
                    body=body,
                    timeout_seconds=resolved.enrichment_timeout_seconds,
                )
            parsed = content_from_response(raw_response)
            if snapshot_digest(current) != snapshot.id:
                raise SeoEnrichmentRejected("AI_STP_SEO_SOURCE_STALE", "source digest drifted")
            try:
                output = validate_enrichment_output(
                    parsed,
                    snapshot=dict(snapshot.facts),
                    base=profile,
                    source_digest=snapshot.source_digest,
                )
                break
            except SeoEnrichmentRejected as exc:
                _log.info(
                    "seo_enrichment_candidate_rejected",
                    subject_kind=kind,
                    subject_id=subject_id,
                    locale=locale,
                    attempt=attempt + 1,
                    reason=str(exc),
                )
                if (
                    exc.code != "AI_STP_SEO_OUTPUT_INVALID"
                    or attempt + 1 == MAX_ENRICHMENT_ATTEMPTS
                ):
                    raise
                feedback = f"Previous candidate rejected: {exc}. Regenerate from the facts."
        if output is None:
            raise SeoEnrichmentRejected("AI_STP_SEO_OUTPUT_INVALID", "no accepted candidate")
        await apply_enrichment(
            session,
            snapshot=snapshot,
            base=profile,
            output=output,
            settings=resolved,
            now=moment,
        )
        prompt_tokens, completion_tokens = usage_from_response(raw_response)
        record_seo_enrich(
            outcome="active",
            duration_ms=int((monotonic() - started) * 1000),
            model_alias=resolved.enrichment_model_alias,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except SeoEnrichmentRejected as exc:
        retryable = exc.code == "AI_STP_SEO_ENRICHMENT_UNAVAILABLE"
        if retryable:
            record_seo_enrich(
                outcome="unavailable",
                duration_ms=int((monotonic() - started) * 1000),
                model_alias=resolved.enrichment_model_alias,
            )
            raise
        state = "stale" if exc.code == "AI_STP_SEO_SOURCE_STALE" else "rejected"
        await persist_rejected(
            session,
            snapshot=snapshot,
            base=profile,
            settings=resolved,
            state=state,
            error_code=exc.code,
            now=moment,
        )
        record_seo_enrich(
            outcome=state if state == "stale" else exc.code,
            duration_ms=int((monotonic() - started) * 1000),
            model_alias=resolved.enrichment_model_alias,
        )


async def _base_profile(
    session: AsyncSession,
    snapshot: SeoFactSnapshot,
    *,
    template_version: str,
) -> SeoProfileDocument:
    row = await session.scalar(
        select(SeoRevision).where(
            SeoRevision.snapshot_id == snapshot.id,
            SeoRevision.generator_kind == "template",
            SeoRevision.template_version == template_version,
        )
    )
    if row is None:
        raise SubjectMissing(snapshot.subject_id)
    return SeoProfileDocument.model_validate(row.profile)
