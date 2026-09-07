"""Conservative public projection of complete target assessment identities."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from typing import cast, get_args

from ai_stp_contracts.assurance import (
    AssessmentState,
    PublicEvidenceRef,
    SupportedArch,
    SupportedOs,
    TargetAssessmentIdentity,
)
from ai_stp_contracts.safety_checks import SafetyCheckEntry
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import DIGEST_PATTERN, digest_canonical
from ai_stp_foundation.invariants import target_assessment_key_digest
from ai_stp_foundation.provider_surfaces import provider_surface
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ComponentVersionPassport, ScopeAdaptation
from ai_stp_platform.catalog_targets import EffectiveAssessment, stale_if_expired
from ai_stp_platform.models import CatalogMetadata, TargetAssessment, TargetAssessmentLatest
from ai_stp_platform.safety.policy import POLICY_VERSION

_TYPE_OS = cast(tuple[str, ...], get_args(SupportedOs.__value__))
_TYPE_ARCH = cast(tuple[str, ...], get_args(SupportedArch.__value__))
ASSESSMENT_STATE_PRIORITY = {"verified": 0, "stale": 1, "not_verified": 2, "failed": 3}
_CHECK_PRIORITY = {
    "passed": 0,
    "not_applicable": 0,
    "skipped": 0,
    "expired": 1,
    "not_run": 2,
    "degraded": 3,
    "warning": 4,
    "failed": 5,
}


@dataclass(frozen=True)
class _Candidate:
    context: tuple[str, str, str]
    current: bool
    state: AssessmentState
    history: TargetAssessment
    identity: TargetAssessmentIdentity


def assessment_passport(meta: CatalogMetadata) -> ComponentVersionPassport | None:
    """An evidence join cannot authorize a changed passport or revision seal."""
    document = meta.passport_document
    if not isinstance(document, dict):
        return None
    raw = cast(dict[str, JsonValue], document)
    try:
        passport = ComponentVersionPassport.model_validate(raw)
        if (
            passport.stable_id != meta.stable_id
            or passport.version != meta.version
            or passport.revision_id != derive_revision_id(raw)
            or meta.passport_digest != digest_canonical("ai-stp:passport:v1", raw)
        ):
            return None
    except ValueError:
        return None
    return passport


def _required_contexts(scope: ScopeAdaptation) -> set[tuple[str, str, str]]:
    return set(
        product(
            scope.supported_harness_versions or ("unspecified",),
            scope.supported_os or _TYPE_OS,
            scope.supported_arch or _TYPE_ARCH,
        )
    )


def _candidate(
    passport: ComponentVersionPassport,
    passport_digest: str,
    adaptation_id: str,
    harness_id: str,
    scope: ScopeAdaptation,
    latest: TargetAssessmentLatest,
    history: TargetAssessment,
    *,
    now: datetime,
) -> _Candidate | None:
    try:
        identity = TargetAssessmentIdentity.model_validate(history.identity)
    except ValueError:
        return None
    key = target_assessment_key_digest(cast(dict[str, JsonValue], identity.model_dump(mode="json")))
    if (
        key != latest.target_key_digest
        or key != history.target_key_digest
        or identity.component_stable_id != passport.stable_id
        or identity.version != passport.version
        or identity.passport_digest != passport_digest
        or identity.adaptation_id != adaptation_id
        or identity.harness_id != harness_id
        or identity.scope != scope.scope
        or identity.target_scope != scope.scope
        or identity.projection_artifact_digest != scope.projection_artifact.digest
        or identity.provider_id != "ai-stp-publication"
        or identity.surface_profile_id != scope.required_surface.profile_id
        or identity.surface_profile_digest != scope.required_surface.profile_digest
        or latest.component_stable_id != identity.component_stable_id
        or latest.version != identity.version
        or latest.adaptation_id != identity.adaptation_id
        or latest.harness_id != identity.harness_id
        or latest.scope != identity.scope
        or history.observed_at > now
    ):
        return None
    context = (identity.harness_version, identity.operating_system, identity.architecture)
    if context not in _required_contexts(scope):
        return None
    surface = provider_surface(identity.harness_id, identity.target_scope)
    current = (
        identity.provider_version == "1"
        and identity.policy_version == POLICY_VERSION
        and identity.surface_profile_id == surface.profile_id
        and identity.surface_profile_digest == surface.profile_digest
    )
    state = (
        stale_if_expired(history.stored_state, history.expires_at, now=now) if current else "stale"
    )
    return _Candidate(context, current, state, history, identity)


def _public_refs(candidates: Sequence[_Candidate]) -> tuple[PublicEvidenceRef, ...]:
    found: dict[tuple[str, str], PublicEvidenceRef] = {}
    for candidate in candidates:
        identity = candidate.identity
        values = [
            PublicEvidenceRef(kind="digest", value=identity.projection_artifact_digest),
            PublicEvidenceRef(kind="profile", value=identity.surface_profile_digest),
        ]
        if identity.policy_version == POLICY_VERSION:
            values.append(PublicEvidenceRef(kind="policy", value=identity.policy_version))
        values.extend(
            PublicEvidenceRef(kind="digest", value=value)
            for value in candidate.history.evidence_refs
            if re.fullmatch(DIGEST_PATTERN, value)
        )
        for value in values:
            found[(value.kind, value.value)] = value
    return tuple(found[key] for key in sorted(found))


def _public_checks(candidates: Sequence[_Candidate]) -> tuple[SafetyCheckEntry, ...]:
    checks: dict[str, SafetyCheckEntry] = {}
    for candidate in candidates:
        summary = candidate.history.checks_summary
        raw = summary.get("checks") if isinstance(summary, dict) else None
        if not isinstance(raw, list):
            continue
        for value in cast(list[object], raw):
            if not isinstance(value, dict):
                continue
            try:
                entry = SafetyCheckEntry.model_validate(
                    {
                        key: item
                        for key, item in cast(dict[str, object], value).items()
                        if key in SafetyCheckEntry.model_fields
                    }
                )
            except ValueError:
                continue
            previous = checks.get(entry.check_id)
            if previous is None or _CHECK_PRIORITY.get(entry.result, 5) > _CHECK_PRIORITY.get(
                previous.result, 5
            ):
                checks[entry.check_id] = entry
    return tuple(checks[key] for key in sorted(checks))


def project_scope_assessments(
    meta: CatalogMetadata,
    records: Sequence[tuple[TargetAssessmentLatest, TargetAssessment]],
    *,
    now: datetime,
) -> dict[tuple[str, str, str], EffectiveAssessment]:
    """Aggregate every required context; row order and foreign targets cannot verify it."""
    passport = assessment_passport(meta)
    if passport is None:
        return {}
    return project_passport_assessments(passport, str(meta.passport_digest), records, now=now)


def project_passport_assessments(
    passport: ComponentVersionPassport,
    passport_digest: str,
    records: Sequence[tuple[TargetAssessmentLatest, TargetAssessment]],
    *,
    now: datetime,
) -> dict[tuple[str, str, str], EffectiveAssessment]:
    """Project a validated exact passport before or after publication."""
    projected: dict[tuple[str, str, str], EffectiveAssessment] = {}
    for adaptation in passport.adaptations:
        for scope in adaptation.scope_adaptations:
            by_context: dict[tuple[str, str, str], _Candidate] = {}
            for latest, history in records:
                candidate = _candidate(
                    passport,
                    passport_digest,
                    adaptation.adaptation_id,
                    adaptation.harness_id,
                    scope,
                    latest,
                    history,
                    now=now,
                )
                if candidate is None:
                    continue
                previous = by_context.get(candidate.context)
                rank = (
                    candidate.current,
                    candidate.history.observed_at,
                    ASSESSMENT_STATE_PRIORITY[candidate.state],
                )
                if previous is None or rank > (
                    previous.current,
                    previous.history.observed_at,
                    ASSESSMENT_STATE_PRIORITY[previous.state],
                ):
                    by_context[candidate.context] = candidate
            candidates = list(by_context.values())
            states: list[AssessmentState] = [candidate.state for candidate in candidates]
            if _required_contexts(scope) - by_context.keys():
                states.append("not_verified")
            state = max(states, key=lambda item: ASSESSMENT_STATE_PRIORITY[item])
            key = (adaptation.adaptation_id, adaptation.harness_id, scope.scope)
            projected[key] = EffectiveAssessment(
                adaptation_id=adaptation.adaptation_id,
                harness_id=adaptation.harness_id,
                scope=scope.scope,
                state=state,
                freshness=format_timestamp(min(item.history.observed_at for item in candidates))
                if candidates
                else None,
                expires_at=min(
                    (item.history.expires_at for item in candidates if item.history.expires_at),
                    default=None,
                ),
                evidence_refs=_public_refs(candidates),
                safety_checks=_public_checks(candidates),
            )
    return projected
