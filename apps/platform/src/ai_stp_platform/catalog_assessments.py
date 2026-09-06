"""Target-bound assessment ingestion and latest-effective reads (SPEC-064)."""

from __future__ import annotations

import hashlib
import platform
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.assurance import (
    ArtifactObservation,
    ArtifactObservationIdentity,
    AssessmentState,
    PublicEvidenceRef,
    SupportedArch,
    SupportedOs,
    TargetAssessmentIdentity,
    TargetAssessmentIngestRequest,
    TargetAssessmentIngestResponse,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.invariants import target_assessment_key_digest
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_passports.versions import ComponentVersionPassport, ScopeAdaptation
from ai_stp_platform.catalog_targets import (
    EffectiveAssessment,
    assurance_counts,
    conservative_component_verified,
    project_target_matrix,
    stale_if_expired,
)
from ai_stp_platform.models import (
    ArtifactObservation as ObservationRow,
)
from ai_stp_platform.models import (
    CatalogMetadata,
    CatalogSearchProjection,
    TargetAssessment,
    TargetAssessmentLatest,
)
from ai_stp_platform.safety.types import SafetyScanResult

_SCANNER_ID = "ai-stp-safety"
_PUBLICATION_PROVIDER_ID = "ai-stp-publication"
_PUBLICATION_PROVIDER_VERSION = "1"
_MAX_OBSERVATIONS = 32


class AssessmentError(ValueError):
    """Rejected evidence that must not advance the latest-effective pointer."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _identity_digest(identity: TargetAssessmentIdentity) -> str:
    payload = cast(dict[str, JsonValue], identity.model_dump(mode="json"))
    return target_assessment_key_digest(payload)


def _observation_digest(identity: ArtifactObservationIdentity) -> str:
    payload = cast(dict[str, JsonValue], identity.model_dump(mode="json"))
    return target_assessment_key_digest({"observation": payload})


def scan_host_platform() -> tuple[SupportedOs, SupportedArch]:
    """OS/arch of the worker that ran the suite. Bound into the target key."""
    system = sys.platform
    machine = platform.machine().lower()
    os_name: SupportedOs
    if system.startswith("linux"):
        os_name = "linux"
    elif system == "darwin":
        os_name = "macos"
    elif system.startswith("win"):
        os_name = "windows"
    else:
        os_name = "linux"
    arch: SupportedArch = "arm64" if machine in {"arm64", "aarch64"} else "x86_64"
    return os_name, arch


def stored_state_from_scan(scan: SafetyScanResult | None) -> tuple[str, str | None]:
    """Map one projection scan onto an assessment stored state."""
    if scan is None:
        return "not_verified", "projection_artifact_unavailable"
    mandatory = [outcome for outcome in scan.outcomes if outcome.mandatory]
    if not mandatory:
        return "not_verified", "safety_incomplete"
    results = [outcome.result for outcome in mandatory]
    if any(result == "failed" for result in results):
        return "failed", "safety_failed"
    if any(result in {"not_run", "degraded", "warning", "running"} for result in results):
        return "not_verified", "safety_incomplete"
    if all(result in {"passed", "skipped", "not_applicable"} for result in results):
        return "verified", None
    return "not_verified", "safety_incomplete"


def _publication_idempotency_key(plan_id: str, target_key: str) -> str:
    digest = hashlib.sha256(f"{plan_id}:{target_key}".encode()).hexdigest()
    return f"va.{digest[:40]}"


def _harness_version(scope: ScopeAdaptation) -> str:
    versions = [item for item in scope.supported_harness_versions if item]
    return versions[0] if versions else "unspecified"


def _observations_from_scan(
    scan: SafetyScanResult,
    *,
    operating_system: SupportedOs,
    architecture: SupportedArch,
    observed_at: str,
    expires_at: str | None,
) -> list[ArtifactObservation]:
    rows: list[ArtifactObservation] = []
    for outcome in scan.outcomes:
        if outcome.result not in {"passed", "failed"}:
            continue
        check_id = outcome.check_id[:64] or "safety_suite"
        scanner_version = (outcome.tool_version or scan.policy_version)[:64] or scan.policy_version
        rows.append(
            ArtifactObservation(
                identity=ArtifactObservationIdentity(
                    artifact_digest=scan.content_digest,  # type: ignore[arg-type]
                    check_id=check_id,
                    scanner_id=_SCANNER_ID,
                    scanner_version=scanner_version,
                    policy_version=scan.policy_version,
                    operating_system=operating_system,
                    architecture=architecture,
                ),
                result=outcome.result,  # type: ignore[arg-type]
                observed_at=observed_at,  # type: ignore[arg-type]
                expires_at=expires_at,  # type: ignore[arg-type]
            )
        )
        if len(rows) >= _MAX_OBSERVATIONS:
            break
    return rows


def _target_identity(
    passport: ComponentVersionPassport,
    *,
    passport_digest: str,
    adaptation_id: str,
    harness_id: str,
    scope: ScopeAdaptation,
    policy_version: str,
    operating_system: SupportedOs,
    architecture: SupportedArch,
) -> TargetAssessmentIdentity:
    surface = scope.required_surface
    return TargetAssessmentIdentity(
        component_stable_id=passport.stable_id,  # type: ignore[arg-type]
        version=passport.version,  # type: ignore[arg-type]
        passport_digest=passport_digest,  # type: ignore[arg-type]
        adaptation_id=adaptation_id,  # type: ignore[arg-type]
        harness_id=harness_id,  # type: ignore[arg-type]
        scope=scope.scope,
        projection_artifact_digest=scope.projection_artifact.digest,  # type: ignore[arg-type]
        provider_id=_PUBLICATION_PROVIDER_ID,
        provider_version=_PUBLICATION_PROVIDER_VERSION,
        surface_profile_id=surface.profile_id,
        surface_profile_digest=surface.profile_digest,  # type: ignore[arg-type]
        target_scope=scope.scope,
        harness_version=_harness_version(scope),
        operating_system=operating_system,
        architecture=architecture,
        policy_version=policy_version,
    )


async def _existing_observation(session: AsyncSession, digest: str) -> ObservationRow | None:
    result: object = await session.execute(
        select(ObservationRow).where(ObservationRow.identity_digest == digest)
    )
    getter = getattr(result, "scalar_one_or_none", None)
    if not callable(getter):
        return None
    existing_raw: object = cast(Callable[[], object], getter)()
    if isinstance(existing_raw, Awaitable):
        existing_raw = await cast(Awaitable[object], existing_raw)
    return existing_raw if isinstance(existing_raw, ObservationRow) else None


async def _store_observation(session: AsyncSession, observation: ArtifactObservation) -> None:
    digest = _observation_digest(observation.identity)
    existing = await _existing_observation(session, digest)
    if existing is not None:
        if existing.result != observation.result:
            raise AssessmentError(
                "AI_STP_CONFLICT", "artifact observation identity already has a conflicting result"
            )
        return
    session.add(
        ObservationRow(
            identity_digest=digest,
            artifact_digest=observation.identity.artifact_digest,
            check_id=observation.identity.check_id,
            scanner_id=observation.identity.scanner_id,
            scanner_version=observation.identity.scanner_version,
            policy_version=observation.identity.policy_version,
            operating_system=observation.identity.operating_system,
            architecture=observation.identity.architecture,
            result=observation.result,
            observed_at=datetime.fromisoformat(observation.observed_at.replace("Z", "+00:00")),
            expires_at=(
                datetime.fromisoformat(observation.expires_at.replace("Z", "+00:00"))
                if observation.expires_at
                else None
            ),
        )
    )


async def ingest_assessment(
    session: AsyncSession, body: TargetAssessmentIngestRequest
) -> TargetAssessmentIngestResponse:
    """Append evidence and atomically advance the latest-effective projection."""
    key = _identity_digest(body.identity)
    replay = (
        await session.execute(
            select(TargetAssessment).where(TargetAssessment.idempotency_key == body.idempotency_key)
        )
    ).scalar_one_or_none()
    if replay is not None:
        if replay.target_key_digest != key or replay.stored_state != body.stored_state:
            raise AssessmentError("AI_STP_CONFLICT", "idempotency key payload does not match")
        latest = await session.get(TargetAssessmentLatest, key)
        state: AssessmentState = (
            stale_if_expired(replay.stored_state, replay.expires_at, now=datetime.now(UTC))
            if latest is not None
            else "not_verified"
        )
        return TargetAssessmentIngestResponse(
            target_key_digest=key,  # type: ignore[arg-type]
            stored_state=replay.stored_state,  # type: ignore[arg-type]
            effective_state=state,
            created=False,
        )
    for observation in body.observations:
        await _store_observation(session, observation)
    observed_at = datetime.fromisoformat(body.observed_at.replace("Z", "+00:00"))
    expires_at = (
        datetime.fromisoformat(body.expires_at.replace("Z", "+00:00")) if body.expires_at else None
    )
    row = TargetAssessment(
        target_key_digest=key,
        identity=body.identity.model_dump(mode="json"),
        stored_state=body.stored_state,
        compatibility_result=body.compatibility_result,
        reason_code=body.reason_code,
        evidence_refs=list(body.evidence_refs),
        observed_at=observed_at,
        expires_at=expires_at,
        idempotency_key=body.idempotency_key,
    )
    session.add(row)
    await session.flush()
    latest = await session.get(TargetAssessmentLatest, key)
    if latest is None:
        session.add(
            TargetAssessmentLatest(
                target_key_digest=key,
                assessment_id=row.id,
                component_stable_id=body.identity.component_stable_id,
                version=body.identity.version,
                adaptation_id=body.identity.adaptation_id,
                harness_id=body.identity.harness_id,
                scope=body.identity.scope,
                stored_state=body.stored_state,
                expires_at=expires_at,
                updated_at=datetime.now(UTC),
            )
        )
    else:
        latest.assessment_id = row.id
        latest.stored_state = body.stored_state
        latest.expires_at = expires_at
        latest.updated_at = datetime.now(UTC)
    await session.flush()
    await _refresh_ingested_version(
        session,
        component_stable_id=body.identity.component_stable_id,
        version=body.identity.version,
    )
    return TargetAssessmentIngestResponse(
        target_key_digest=key,  # type: ignore[arg-type]
        stored_state=body.stored_state,
        effective_state=stale_if_expired(body.stored_state, expires_at, now=datetime.now(UTC)),
        created=True,
    )


async def load_effective_assessments_for_versions(
    session: AsyncSession, versions: Sequence[tuple[str, str]]
) -> dict[tuple[str, str, str, str, str], EffectiveAssessment]:
    """Latest-effective rows keyed by stable_id, version, adaptation, harness, scope."""
    if not versions:
        return {}
    now = datetime.now(UTC)
    rows = list(
        (
            await session.execute(
                select(TargetAssessmentLatest).where(
                    tuple_(
                        TargetAssessmentLatest.component_stable_id,
                        TargetAssessmentLatest.version,
                    ).in_(list(versions))
                )
            )
        )
        .scalars()
        .all()
    )
    history_ids = [row.assessment_id for row in rows]
    histories: dict[int, TargetAssessment] = {}
    if history_ids:
        history_rows = list(
            (
                await session.execute(
                    select(TargetAssessment).where(TargetAssessment.id.in_(history_ids))
                )
            )
            .scalars()
            .all()
        )
        histories = {row.id: row for row in history_rows}
    result: dict[tuple[str, str, str, str, str], EffectiveAssessment] = {}
    for row in rows:
        history = histories.get(row.assessment_id)
        refs = (
            [PublicEvidenceRef(kind="digest", value=item) for item in history.evidence_refs]
            if history is not None
            else []
        )
        result[
            (
                row.component_stable_id,
                row.version,
                row.adaptation_id,
                row.harness_id,
                row.scope,
            )
        ] = EffectiveAssessment(
            adaptation_id=row.adaptation_id,
            harness_id=row.harness_id,
            scope=row.scope,
            state=stale_if_expired(row.stored_state, row.expires_at, now=now),
            freshness=history.observed_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            if history is not None
            else None,
            evidence_refs=tuple(refs),
        )
    return result


async def load_effective_assessments(
    session: AsyncSession, *, component_stable_id: str, version: str
) -> dict[tuple[str, str, str], EffectiveAssessment]:
    """Latest-effective rows for one exact component version."""
    loaded = await load_effective_assessments_for_versions(
        session, [(component_stable_id, version)]
    )
    return {
        (adaptation_id, harness_id, scope): item
        for (_stable_id, _version, adaptation_id, harness_id, scope), item in loaded.items()
    }


async def apply_component_verified(session: AsyncSession, meta: CatalogMetadata) -> bool:
    """Recompute conservative component_verified for one catalog version row."""
    document = meta.passport_document
    version = meta.version
    if meta.object_kind != "component" or not isinstance(document, dict) or not version:
        return bool(meta.component_verified)
    try:
        passport = ComponentVersionPassport.model_validate(document)
    except (TypeError, ValueError):
        return False
    assessments = await load_effective_assessments(
        session, component_stable_id=meta.stable_id, version=version
    )
    matrix = project_target_matrix(passport, assessments=assessments, include_risk_command=False)
    verified = conservative_component_verified(checks_summary=meta.checks_summary, matrix=matrix)
    meta.component_verified = verified
    return verified


async def refresh_component_assurance(
    session: AsyncSession, meta: CatalogMetadata, row: CatalogSearchProjection
) -> None:
    """Fill search-projection assurance fields from latest-effective assessments."""
    document = meta.passport_document
    version = meta.version
    if meta.object_kind != "component" or not isinstance(document, dict) or not version:
        return
    try:
        passport = ComponentVersionPassport.model_validate(document)
    except (TypeError, ValueError):
        return
    assessments = await load_effective_assessments(
        session, component_stable_id=meta.stable_id, version=version
    )
    matrix = project_target_matrix(passport, assessments=assessments, include_risk_command=False)
    counts = assurance_counts(matrix)
    verified = conservative_component_verified(checks_summary=meta.checks_summary, matrix=matrix)
    meta.component_verified = verified
    row.verified_targets = counts.verified_targets
    row.assessed_targets = counts.assessed_targets
    row.component_verified = verified


async def _refresh_ingested_version(
    session: AsyncSession, *, component_stable_id: str, version: str
) -> None:
    meta = (
        await session.execute(
            select(CatalogMetadata).where(
                CatalogMetadata.object_kind == "component",
                CatalogMetadata.stable_id == component_stable_id,
                CatalogMetadata.version == version,
            )
        )
    ).scalar_one_or_none()
    if meta is not None:
        await apply_component_verified(session, meta)
    from ai_stp_platform.catalog_search import upsert_catalog_search_projection

    await upsert_catalog_search_projection(
        session, object_kind="component", stable_id=component_stable_id
    )


async def record_component_scan_assessments(
    session: AsyncSession,
    *,
    plan_id: str,
    passport: ComponentVersionPassport,
    passport_digest: str,
    policy_version: str,
    scans_by_digest: Mapping[str, SafetyScanResult],
    expires_at: datetime,
) -> None:
    """Write one target assessment per exact adaptation/scope from worker scans.

    Publication input still cannot set verified by itself: the stored state
    comes only from the platform safety suite for that projection's bytes.
    Missing projection bytes stay ``not_verified``. A failed projection does
    not rewrite another projection's state.
    """
    if not passport.adaptations:
        return
    operating_system, architecture = scan_host_platform()
    observed_at = datetime.now(UTC)
    observed_wire = format_timestamp(observed_at)
    expires_wire = format_timestamp(expires_at)
    seen_observations: set[str] = set()
    for adaptation in passport.adaptations:
        for scope in adaptation.scope_adaptations:
            digest = scope.projection_artifact.digest
            scan = scans_by_digest.get(digest)
            stored_state, reason_code = stored_state_from_scan(scan)
            identity = _target_identity(
                passport,
                passport_digest=passport_digest,
                adaptation_id=adaptation.adaptation_id,
                harness_id=adaptation.harness_id,
                scope=scope,
                policy_version=policy_version,
                operating_system=operating_system,
                architecture=architecture,
            )
            key = _identity_digest(identity)
            observations: list[ArtifactObservation] = []
            if scan is not None:
                observations = _observations_from_scan(
                    scan,
                    operating_system=operating_system,
                    architecture=architecture,
                    observed_at=observed_wire,
                    expires_at=expires_wire,
                )
            for observation in observations:
                digest_key = _observation_digest(observation.identity)
                if digest_key in seen_observations:
                    continue
                seen_observations.add(digest_key)
                await _store_observation(session, observation)
            evidence_refs = [digest, policy_version]
            row = TargetAssessment(
                target_key_digest=key,
                identity=identity.model_dump(mode="json"),
                stored_state=stored_state,
                compatibility_result="not_run",
                reason_code=reason_code,
                evidence_refs=evidence_refs,
                observed_at=observed_at,
                expires_at=expires_at,
                idempotency_key=_publication_idempotency_key(plan_id, key),
            )
            session.add(row)
            await session.flush()
            session.add(
                TargetAssessmentLatest(
                    target_key_digest=key,
                    assessment_id=row.id,
                    component_stable_id=passport.stable_id,
                    version=passport.version,
                    adaptation_id=adaptation.adaptation_id,
                    harness_id=adaptation.harness_id,
                    scope=scope.scope,
                    stored_state=stored_state,
                    expires_at=expires_at,
                    updated_at=observed_at,
                )
            )
    await session.flush()
