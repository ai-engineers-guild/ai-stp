"""Target-bound assessment ingestion and latest-effective reads (SPEC-064)."""

from __future__ import annotations

import hashlib
import platform
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import and_, case, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.assurance import (
    ArtifactObservation,
    ArtifactObservationIdentity,
    AssessmentState,
    SupportedArch,
    SupportedOs,
    TargetAssessmentIdentity,
    TargetAssessmentIngestRequest,
    TargetAssessmentIngestResponse,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.invariants import target_assessment_key_digest
from ai_stp_foundation.provider_surfaces import provider_surface
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_passports.projections import ProjectionArtifactError, verify_projection
from ai_stp_passports.versions import ComponentVersionPassport, ScopeAdaptation, adaptation_for
from ai_stp_platform.assessment_projection import ASSESSMENT_STATE_PRIORITY
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
    EvidenceBinding,
    PublicationPlan,
    TargetAssessment,
    TargetAssessmentLatest,
    ValidationSnapshot,
)
from ai_stp_platform.safety.percent import build_checks_summary
from ai_stp_platform.safety.policy import POLICY_VERSION
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


async def _validate_published_identity(
    session: AsyncSession, identity: TargetAssessmentIdentity
) -> None:
    """Validate every writer-supplied target field against canonical catalog data."""
    meta = (
        await session.execute(
            select(CatalogMetadata).where(
                CatalogMetadata.object_kind == "component",
                CatalogMetadata.stable_id == identity.component_stable_id,
                CatalogMetadata.version == identity.version,
                CatalogMetadata.visibility == "public",
                CatalogMetadata.lifecycle_state.in_(("active", "deprecated")),
                CatalogMetadata.published_at.is_not(None),
            )
        )
    ).scalar_one_or_none()
    if meta is None or meta.passport_document is None or meta.passport_digest is None:
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "assessment target is not published")
    if identity.passport_digest != meta.passport_digest:
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "passport digest is not canonical")
    try:
        passport = ComponentVersionPassport.model_validate(meta.passport_document)
        adaptation = adaptation_for(passport, identity.harness_id)
    except (TypeError, ValueError) as exc:
        raise AssessmentError(
            "AI_STP_VALIDATION_ERROR", "published adaptation is unavailable"
        ) from exc
    if passport.stable_id != identity.component_stable_id or passport.version != identity.version:
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "component identity is not canonical")
    if adaptation.adaptation_id != identity.adaptation_id:
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "adaptation identity is not canonical")
    scope = next(
        (item for item in adaptation.scope_adaptations if item.scope == identity.scope), None
    )
    if scope is None or identity.target_scope != scope.scope:
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "target scope is not canonical")
    if identity.projection_artifact_digest != scope.projection_artifact.digest:
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "projection digest is not canonical")
    if identity.provider_id != _PUBLICATION_PROVIDER_ID:
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "provider is not canonical")
    if identity.provider_version != _PUBLICATION_PROVIDER_VERSION:
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "provider version is not canonical")
    try:
        surface = provider_surface(identity.harness_id, identity.target_scope)
    except KeyError as exc:
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "provider surface is unknown") from exc
    required_surface = scope.required_surface
    if (
        identity.surface_profile_id != required_surface.profile_id
        or identity.surface_profile_digest != required_surface.profile_digest
        or required_surface.profile_id != surface.profile_id
        or required_surface.profile_digest != surface.profile_digest
    ):
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "surface profile is not canonical")
    if identity.policy_version != POLICY_VERSION:
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "policy version is stale or unknown")
    allowed_versions = set(scope.supported_harness_versions)
    if (allowed_versions and identity.harness_version not in allowed_versions) or (
        not allowed_versions and identity.harness_version != "unspecified"
    ):
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "harness version is not allowed")
    if scope.supported_os and identity.operating_system not in scope.supported_os:
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "operating system is not allowed")
    if scope.supported_arch and identity.architecture not in scope.supported_arch:
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "architecture is not allowed")


async def _upsert_latest(
    session: AsyncSession,
    *,
    key: str,
    assessment_id: int,
    identity: TargetAssessmentIdentity,
    stored_state: str,
    expires_at: datetime | None,
    updated_at: datetime,
) -> None:
    """Keep one latest pointer; an older event cannot win a concurrent race."""
    statement = (
        insert(TargetAssessmentLatest)
        .values(
            target_key_digest=key,
            assessment_id=assessment_id,
            component_stable_id=identity.component_stable_id,
            version=identity.version,
            adaptation_id=identity.adaptation_id,
            harness_id=identity.harness_id,
            scope=identity.scope,
            stored_state=stored_state,
            expires_at=expires_at,
            updated_at=updated_at,
        )
        .on_conflict_do_update(
            index_elements=[TargetAssessmentLatest.target_key_digest],
            set_={
                "assessment_id": assessment_id,
                "stored_state": stored_state,
                "expires_at": expires_at,
                "updated_at": updated_at,
            },
            where=or_(
                TargetAssessmentLatest.updated_at < updated_at,
                and_(
                    TargetAssessmentLatest.updated_at == updated_at,
                    case(
                        ASSESSMENT_STATE_PRIORITY,
                        value=TargetAssessmentLatest.stored_state,
                        else_=2,
                    )
                    < ASSESSMENT_STATE_PRIORITY.get(stored_state, 2),
                ),
            ),
        )
    )
    await session.execute(statement)


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
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "assessment worker OS is unsupported")
    arch: SupportedArch
    if machine in {"arm64", "aarch64"}:
        arch = "arm64"
    elif machine in {"x86_64", "amd64"}:
        arch = "x86_64"
    else:
        raise AssessmentError(
            "AI_STP_VALIDATION_ERROR", "assessment worker architecture is unsupported"
        )
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
        harness_version="unspecified",
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
    await session.execute(
        select(
            func.pg_advisory_xact_lock(func.hashtextextended("artifact-observation:" + digest, 0))
        )
    )
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


def _validate_ingest_evidence(body: TargetAssessmentIngestRequest, *, now: datetime) -> None:
    observed_at = datetime.fromisoformat(body.observed_at.replace("Z", "+00:00"))
    if observed_at > now:
        raise AssessmentError("AI_STP_VALIDATION_ERROR", "assessment observation is in the future")
    if (
        body.expires_at is not None
        and datetime.fromisoformat(body.expires_at.replace("Z", "+00:00")) <= observed_at
    ):
        raise AssessmentError(
            "AI_STP_VALIDATION_ERROR", "assessment expiry precedes its observation"
        )
    if body.stored_state == "verified" and body.compatibility_result == "failed":
        raise AssessmentError(
            "AI_STP_VALIDATION_ERROR", "failed compatibility cannot verify a target"
        )
    for observation in body.observations:
        identity = observation.identity
        moment = datetime.fromisoformat(observation.observed_at.replace("Z", "+00:00"))
        expiry = (
            datetime.fromisoformat(observation.expires_at.replace("Z", "+00:00"))
            if observation.expires_at
            else None
        )
        if (
            identity.artifact_digest != body.identity.projection_artifact_digest
            or identity.policy_version != body.identity.policy_version
            or identity.operating_system not in {None, body.identity.operating_system}
            or identity.architecture not in {None, body.identity.architecture}
            or moment > observed_at
            or (expiry is not None and expiry <= moment)
            or (body.stored_state == "verified" and observation.result == "failed")
        ):
            raise AssessmentError(
                "AI_STP_VALIDATION_ERROR",
                "artifact observation does not match its target assessment",
            )


async def ingest_assessment(
    session: AsyncSession, body: TargetAssessmentIngestRequest
) -> TargetAssessmentIngestResponse:
    """Append evidence and atomically advance the latest-effective projection."""
    await session.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended("target-assessment-ingest:" + body.idempotency_key, 0)
            )
        )
    )
    await _validate_published_identity(session, body.identity)
    _validate_ingest_evidence(body, now=datetime.now(UTC))
    key = _identity_digest(body.identity)
    payload = cast(dict[str, JsonValue], body.model_dump(mode="json"))
    payload_digest = target_assessment_key_digest({"payload": payload})
    replay = (
        await session.execute(
            select(TargetAssessment).where(TargetAssessment.idempotency_key == body.idempotency_key)
        )
    ).scalar_one_or_none()
    if replay is not None:
        if replay.target_key_digest != key or replay.payload_digest != payload_digest:
            raise AssessmentError("AI_STP_CONFLICT", "idempotency key payload does not match")
        latest = await session.get(TargetAssessmentLatest, key, populate_existing=True)
        state: AssessmentState = (
            stale_if_expired(latest.stored_state, latest.expires_at, now=datetime.now(UTC))
            if latest is not None
            else "not_verified"
        )
        return TargetAssessmentIngestResponse(
            target_key_digest=key,  # type: ignore[arg-type]
            stored_state=replay.stored_state,  # type: ignore[arg-type]
            effective_state=state,
            created=False,
        )
    for observation in sorted(
        body.observations, key=lambda item: _observation_digest(item.identity)
    ):
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
        payload_digest=payload_digest,
    )
    session.add(row)
    await session.flush()
    await _upsert_latest(
        session,
        key=key,
        assessment_id=row.id,
        identity=body.identity,
        stored_state=body.stored_state,
        expires_at=expires_at,
        updated_at=observed_at,
    )
    await session.flush()
    await _refresh_ingested_version(
        session,
        component_stable_id=body.identity.component_stable_id,
        version=body.identity.version,
    )
    latest = await session.get(TargetAssessmentLatest, key, populate_existing=True)
    return TargetAssessmentIngestResponse(
        target_key_digest=key,  # type: ignore[arg-type]
        stored_state=body.stored_state,
        effective_state=stale_if_expired(
            latest.stored_state, latest.expires_at, now=datetime.now(UTC)
        )
        if latest is not None
        else "not_verified",
        created=True,
    )


async def load_effective_assessments_for_versions(
    session: AsyncSession, versions: Sequence[tuple[str, str]]
) -> dict[tuple[str, str, str, str, str], EffectiveAssessment]:
    """Latest-effective rows keyed by stable_id, version, adaptation, harness, scope."""
    if not versions:
        return {}
    from ai_stp_platform.assessment_projection import project_scope_assessments

    now = datetime.now(UTC)
    rows = (
        await session.execute(
            select(TargetAssessmentLatest, TargetAssessment, CatalogMetadata)
            .join(TargetAssessment, TargetAssessment.id == TargetAssessmentLatest.assessment_id)
            .join(
                CatalogMetadata,
                (CatalogMetadata.stable_id == TargetAssessmentLatest.component_stable_id)
                & (CatalogMetadata.version == TargetAssessmentLatest.version)
                & (CatalogMetadata.object_kind == "component"),
            )
            .where(
                tuple_(
                    TargetAssessmentLatest.component_stable_id, TargetAssessmentLatest.version
                ).in_(list(versions)),
                CatalogMetadata.visibility == "public",
                CatalogMetadata.lifecycle_state.in_(("active", "deprecated")),
                CatalogMetadata.published_at.is_not(None),
            )
        )
    ).all()
    grouped: dict[
        int, tuple[CatalogMetadata, list[tuple[TargetAssessmentLatest, TargetAssessment]]]
    ] = {}
    for latest, history, metadata in rows:
        if metadata.id not in grouped:
            grouped[metadata.id] = (metadata, [])
        grouped[metadata.id][1].append((latest, history))
    result: dict[tuple[str, str, str, str, str], EffectiveAssessment] = {}
    for metadata, records in grouped.values():
        for (adaptation_id, harness_id, scope), assessment in project_scope_assessments(
            metadata, records, now=now
        ).items():
            result[
                (metadata.stable_id, str(metadata.version), adaptation_id, harness_id, scope)
            ] = assessment
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


async def assess_passport(
    session: AsyncSession,
    passport: ComponentVersionPassport,
    passport_digest: str,
) -> dict[tuple[str, str, str], EffectiveAssessment]:
    """Read exact target records without requiring an already published metadata row."""
    from ai_stp_platform.assessment_projection import project_passport_assessments

    records = (
        (
            await session.execute(
                select(TargetAssessmentLatest, TargetAssessment)
                .join(TargetAssessment, TargetAssessment.id == TargetAssessmentLatest.assessment_id)
                .where(
                    TargetAssessmentLatest.component_stable_id == passport.stable_id,
                    TargetAssessmentLatest.version == passport.version,
                )
            )
        )
        .tuples()
        .all()
    )
    return project_passport_assessments(passport, passport_digest, records, now=datetime.now(UTC))


async def common_publication_evidence(
    session: AsyncSession, metadata: Sequence[CatalogMetadata], *, now: datetime
) -> dict[int, tuple[bool, datetime | None]]:
    """Current mandatory evidence from the latest published exact-passport snapshot."""
    if not metadata:
        return {}
    coordinates = [(meta.stable_id, meta.version) for meta in metadata]
    records = (
        await session.execute(
            select(PublicationPlan, ValidationSnapshot, EvidenceBinding)
            .join(ValidationSnapshot, ValidationSnapshot.plan_id == PublicationPlan.id)
            .join(EvidenceBinding, EvidenceBinding.snapshot_id == ValidationSnapshot.id)
            .where(
                PublicationPlan.object_kind == "component",
                PublicationPlan.state == "published",
                tuple_(PublicationPlan.stable_id, PublicationPlan.version).in_(coordinates),
                EvidenceBinding.mandatory.is_(True),
            )
            .order_by(ValidationSnapshot.created_at.desc(), ValidationSnapshot.id)
        )
    ).all()
    by_passport: dict[tuple[str, str, str], tuple[str, list[EvidenceBinding]]] = {}
    for plan, snapshot, binding in records:
        try:
            passport = ComponentVersionPassport.model_validate(plan.passport)
        except ValueError:
            continue
        digest = digest_canonical(
            "ai-stp:passport:v1", cast(dict[str, JsonValue], passport.model_dump(mode="json"))
        )
        if snapshot.content_digest != passport.artifact.digest:
            continue
        key = (plan.stable_id, plan.version, digest)
        if key not in by_passport:
            by_passport[key] = (snapshot.id, [])
        if by_passport[key][0] == snapshot.id:
            by_passport[key][1].append(binding)
    result: dict[int, tuple[bool, datetime | None]] = {}
    for meta in metadata:
        _snapshot_id, bindings = by_passport.get(
            (meta.stable_id, str(meta.version), str(meta.passport_digest)), ("", [])
        )
        expiry = min((item.expires_at for item in bindings if item.expires_at), default=None)
        result[meta.id] = (
            bool(bindings)
            and all(item.result == "passed" for item in bindings)
            and (expiry is None or expiry > now),
            expiry,
        )
    return result


async def current_component_verification(
    session: AsyncSession, metadata: Sequence[CatalogMetadata]
) -> dict[int, tuple[bool, datetime | None]]:
    """Batch-read current assurance without mutating published metadata."""
    from ai_stp_platform.assessment_projection import assessment_passport

    components = [meta for meta in metadata if meta.object_kind == "component"]
    assessments = await load_effective_assessments_for_versions(
        session, [(meta.stable_id, str(meta.version)) for meta in components]
    )
    common = await common_publication_evidence(session, components, now=datetime.now(UTC))
    result: dict[int, tuple[bool, datetime | None]] = {}
    for meta in components:
        passport = assessment_passport(meta)
        targets = {
            (adaptation, harness, scope): item
            for (stable_id, version, adaptation, harness, scope), item in assessments.items()
            if stable_id == meta.stable_id and version == meta.version
        }
        passed, common_expiry = common.get(meta.id, (False, None))
        verified = bool(
            passport is not None
            and passed
            and conservative_component_verified(
                checks_summary=meta.checks_summary,
                matrix=project_target_matrix(passport, assessments=targets),
            )
        )
        expiries = [item.expires_at for item in targets.values() if item.expires_at]
        if common_expiry:
            expiries.append(common_expiry)
        result[meta.id] = (verified, min(expiries, default=None))
    return result


async def apply_component_verified(session: AsyncSession, meta: CatalogMetadata) -> bool:
    """Persist the same current badge returned by public reads."""
    verified = await current_component_verification(session, [meta])
    if meta.id in verified:
        meta.component_verified = verified[meta.id][0]
    return bool(meta.component_verified)


async def refresh_component_assurance(
    session: AsyncSession, meta: CatalogMetadata, row: CatalogSearchProjection
) -> None:
    """Fill search-projection assurance fields from latest-effective assessments."""
    from ai_stp_platform.assessment_projection import assessment_passport

    if meta.object_kind != "component":
        return
    passport = assessment_passport(meta)
    assessments = await load_effective_assessments(
        session, component_stable_id=meta.stable_id, version=str(meta.version)
    )
    if passport is not None:
        counts = assurance_counts(project_target_matrix(passport, assessments=assessments))
        row.verified_targets = counts.verified_targets
        row.assessed_targets = counts.assessed_targets
    verified, expiry = (await current_component_verification(session, [meta]))[meta.id]
    meta.component_verified = verified
    row.component_verified = verified
    row.component_verified_expires_at = expiry


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
    payloads_by_digest: Mapping[str, bytes],
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
    observations_by_identity: dict[str, ArtifactObservation] = {}
    for adaptation in passport.adaptations:
        for scope in adaptation.scope_adaptations:
            digest = scope.projection_artifact.digest
            scan = scans_by_digest.get(digest)
            if scan is None:
                continue
            if scan.content_digest != digest or scan.policy_version != policy_version:
                raise AssessmentError("AI_STP_VALIDATION_ERROR", "projection scan identity differs")
            for observation in _observations_from_scan(
                scan,
                operating_system=operating_system,
                architecture=architecture,
                observed_at=observed_wire,
                expires_at=expires_wire,
            ):
                observations_by_identity[_observation_digest(observation.identity)] = observation
    for key in sorted(observations_by_identity):
        await _store_observation(session, observations_by_identity[key])
    for adaptation in passport.adaptations:
        for scope in adaptation.scope_adaptations:
            digest = scope.projection_artifact.digest
            scan = scans_by_digest.get(digest)
            stored_state, reason_code = stored_state_from_scan(scan)
            payload = payloads_by_digest.get(digest)
            projection_invalid = False
            if payload is None:
                stored_state, reason_code = "not_verified", "projection_bytes_unavailable"
            else:
                try:
                    verify_projection(scope, payload)
                except ProjectionArtifactError:
                    stored_state, reason_code = "failed", "projection_integrity_mismatch"
                    projection_invalid = True
            if stored_state == "verified" and scope.supported_harness_versions:
                stored_state, reason_code = "not_verified", "harness_execution_not_observed"
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
            evidence_refs = [digest, policy_version]
            scan_bindings = scan.bindings() if scan is not None else []
            if projection_invalid:
                scan_bindings = [
                    {**check, "result": "failed", "reason": "projection_integrity_mismatch"}
                    if check.get("check_id") == "artifact_unpack"
                    else check
                    for check in scan_bindings
                ]
            checks_summary = build_checks_summary(scan_bindings) if scan_bindings else None
            row = TargetAssessment(
                target_key_digest=key,
                identity=identity.model_dump(mode="json"),
                stored_state=stored_state,
                compatibility_result="not_run",
                reason_code=reason_code,
                checks_summary=checks_summary,
                evidence_refs=evidence_refs,
                observed_at=observed_at,
                expires_at=expires_at,
                idempotency_key=_publication_idempotency_key(plan_id, key),
            )
            session.add(row)
            await session.flush()
            await _upsert_latest(
                session,
                key=key,
                assessment_id=row.id,
                identity=identity,
                stored_state=stored_state,
                expires_at=expires_at,
                updated_at=observed_at,
            )
    await session.flush()
