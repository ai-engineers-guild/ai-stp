"""Project exact and claimed-portable target rows (SPEC-064)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from ai_stp_contracts.assurance import (
    AssessmentState,
    AssuranceCounts,
    ClaimTargetRow,
    ExactTargetRow,
    OwnerTargetGap,
    PublicEvidenceRef,
    RecommendationState,
    TargetMatrix,
    risk_install_command,
)
from ai_stp_contracts.families import SelectedAdaptation, SetupCompositionMember
from ai_stp_passports.versions import (
    ComponentVersionPassport,
    ScopeAdaptation,
    SetupVersionPassport,
    TechnicalSupport,
    adaptation_for,
)


@dataclass(frozen=True)
class EffectiveAssessment:
    """Latest-effective target evidence used by a public matrix row."""

    adaptation_id: str
    harness_id: str
    scope: str
    state: AssessmentState
    freshness: str | None = None
    evidence_refs: tuple[PublicEvidenceRef, ...] = ()


def claimed_harness_ids(passport: dict[str, Any]) -> list[str]:
    """Harnesses named only by current portability claims."""
    exact: set[str] = set()
    raw_adaptations = passport.get("adaptations")
    if isinstance(raw_adaptations, list):
        for item in cast(list[object], raw_adaptations):
            if isinstance(item, dict):
                harness = cast(dict[str, object], item).get("harness_id")
                if isinstance(harness, str):
                    exact.add(harness)
    harness = passport.get("harness_id")
    if isinstance(harness, str) and harness:
        exact.add(harness)
    ordered: list[str] = []
    raw_claims = passport.get("portability_claims")
    if not isinstance(raw_claims, list):
        return ordered
    for claim in cast(list[object], raw_claims):
        if not isinstance(claim, dict):
            continue
        targets = cast(dict[str, object], claim).get("target_harness_ids")
        if not isinstance(targets, list):
            continue
        for target in cast(list[object], targets):
            if isinstance(target, str) and target not in exact and target not in ordered:
                ordered.append(target)
    return ordered


def homogeneous_projection_kind(passport: ComponentVersionPassport) -> str | None:
    """Return the shared projection kind, or None when adaptations differ."""
    kinds = {
        scope.projection_kind
        for adaptation in passport.adaptations
        for scope in adaptation.scope_adaptations
    }
    if len(kinds) != 1:
        return None
    return next(iter(kinds))


def _permissions_summary(scope: ScopeAdaptation) -> list[str]:
    claims: list[str] = []
    for group, items in (
        ("filesystem", scope.permissions.filesystem),
        ("network", scope.permissions.network),
        ("process", scope.permissions.process),
    ):
        for item in items:
            claims.append(f"{group}:{item}")
    return claims


def _recommendation(support: TechnicalSupport, state: AssessmentState) -> RecommendationState:
    if support == "supported" and state == "verified":
        return "recommended"
    if state == "failed":
        return "not_recommended"
    return "ineffective"


def _lookup(
    assessments: dict[tuple[str, str, str], EffectiveAssessment],
    *,
    adaptation_id: str,
    harness_id: str,
    scope: str,
) -> EffectiveAssessment | None:
    return assessments.get((adaptation_id, harness_id, scope))


def project_target_matrix(
    passport: ComponentVersionPassport,
    *,
    assessments: dict[tuple[str, str, str], EffectiveAssessment] | None = None,
    include_risk_command: bool = True,
    now: datetime | None = None,
) -> TargetMatrix:
    """Build the public exact/claim matrix. Missing evidence is not_verified."""
    del now
    rows: list[ExactTargetRow] = []
    found = assessments or {}
    for adaptation in passport.adaptations:
        for scope in adaptation.scope_adaptations:
            evidence = _lookup(
                found,
                adaptation_id=adaptation.adaptation_id,
                harness_id=adaptation.harness_id,
                scope=scope.scope,
            )
            state: AssessmentState = evidence.state if evidence is not None else "not_verified"
            rows.append(
                ExactTargetRow(
                    harness_id=adaptation.harness_id,
                    adaptation_id=adaptation.adaptation_id,  # type: ignore[arg-type]
                    scope=scope.scope,
                    implementation_mode=adaptation.implementation_mode,
                    projection_kind=scope.projection_kind,
                    technical_support=scope.technical_support,
                    technical_support_reason=scope.technical_support_reason,
                    supported_os=list(scope.supported_os),  # type: ignore[arg-type]
                    supported_arch=list(scope.supported_arch),  # type: ignore[arg-type]
                    semantic_losses=list(scope.semantic_losses),
                    permissions_summary=_permissions_summary(scope),
                    assessment_state=state,
                    freshness=evidence.freshness if evidence is not None else None,
                    recommendation=_recommendation(scope.technical_support, state),
                    evidence_refs=list(evidence.evidence_refs) if evidence is not None else [],
                )
            )
    claims: list[ClaimTargetRow] = []
    for claim in passport.portability_claims:
        for harness_id in claim.target_harness_ids:
            command = None
            if include_risk_command:
                command = risk_install_command(
                    stable_id=passport.stable_id,
                    version=passport.version,
                    harness_id=harness_id,
                    claim_id=claim.claim_id,
                )
            claims.append(
                ClaimTargetRow(
                    harness_id=harness_id,
                    claim_id=claim.claim_id,  # type: ignore[arg-type]
                    transform_family=claim.transform_family,
                    transform_version=claim.transform_version,  # type: ignore[arg-type]
                    component_types=list(claim.component_types),
                    scopes=list(claim.scopes),
                    limitations=list(claim.limitations),
                    issued_at=claim.issued_at,  # type: ignore[arg-type]
                    expires_at=claim.expires_at,  # type: ignore[arg-type]
                    evidence_refs=[
                        PublicEvidenceRef(kind="digest", value=item) for item in claim.evidence_refs
                    ],
                    risk_cli_command=command,
                )
            )
    return TargetMatrix(exact=rows, claimed_portable=claims)


def assurance_counts(matrix: TargetMatrix) -> AssuranceCounts:
    """Card summary. Claims never increase the verified numerator."""
    assessed = len(matrix.exact)
    verified = sum(1 for row in matrix.exact if row.assessment_state == "verified")
    return AssuranceCounts(verified_targets=verified, assessed_targets=assessed)


def mandatory_checks_passed(checks_summary: Mapping[str, Any] | None) -> bool:
    """True only when every mandatory safety binding in the summary passed."""
    if not isinstance(checks_summary, dict):
        return False
    checks = checks_summary.get("checks")
    if not isinstance(checks, list) or not checks:
        return False
    rows = [
        cast(dict[str, object], item)
        for item in cast(list[object], checks)
        if isinstance(item, dict)
    ]
    mandatory = [row for row in rows if row.get("mandatory")]
    if not mandatory:
        return False
    return all(row.get("result") == "passed" for row in mandatory)


def conservative_component_verified(
    *, checks_summary: Mapping[str, Any] | None, matrix: TargetMatrix
) -> bool:
    """REQ-6410: mandatory checks and every advertised exact target must be verified.

    Claims never contribute. Mixed, missing, failed, and stale required targets
    produce false without mutating the immutable component version.
    """
    if not mandatory_checks_passed(checks_summary):
        return False
    if not matrix.exact:
        return False
    return all(row.assessment_state == "verified" for row in matrix.exact)


def selected_adaptation_for_setup(
    component: ComponentVersionPassport,
    *,
    harness_id: str,
    assessments: dict[tuple[str, str, str], EffectiveAssessment] | None = None,
) -> SelectedAdaptation:
    """The one adaptation a setup of this harness may pin."""
    adaptation = adaptation_for(component, harness_id)  # type: ignore[arg-type]
    scope = adaptation.scope_adaptations[0]
    evidence = (assessments or {}).get((adaptation.adaptation_id, harness_id, scope.scope))
    state: AssessmentState = evidence.state if evidence is not None else "not_verified"
    return SelectedAdaptation(
        adaptation_id=adaptation.adaptation_id,  # type: ignore[arg-type]
        harness_id=adaptation.harness_id,
        implementation_mode=adaptation.implementation_mode,
        projection_kind=scope.projection_kind,
        technical_support=scope.technical_support,
        scopes=[item.scope for item in adaptation.scope_adaptations],
        assessment_state=state,
        recommendation=_recommendation(scope.technical_support, state),
        limitations=list(scope.semantic_losses),
    )


def missing_exact_adaptation_pins(
    setup: SetupVersionPassport,
    components: Mapping[str, ComponentVersionPassport],
) -> list[str]:
    """Stable IDs that lack an exact adaptation for the setup harness (REQ-6420)."""
    missing: list[str] = []
    for ref in setup.components:
        component = components.get(ref.stable_id)
        if component is None or component.version != ref.version:
            missing.append(ref.stable_id)
            continue
        try:
            adaptation_for(component, setup.harness_id)  # type: ignore[arg-type]
        except ValueError:
            missing.append(ref.stable_id)
    return missing


def setup_composition(
    setup: SetupVersionPassport,
    components: dict[str, ComponentVersionPassport],
    *,
    assessments: dict[tuple[str, str, str], EffectiveAssessment] | None = None,
) -> list[SetupCompositionMember]:
    """Pin each setup member to the adaptation of the setup harness."""
    missing = missing_exact_adaptation_pins(setup, components)
    if missing:
        raise ValueError(f"setup composition missing exact adaptation for {missing[0]}")
    members: list[SetupCompositionMember] = []
    for ref in setup.components:
        component = components[ref.stable_id]
        members.append(
            SetupCompositionMember(
                stable_id=ref.stable_id,  # type: ignore[arg-type]
                version=ref.version,
                passport_digest=ref.passport_digest,  # type: ignore[arg-type]
                selected_adaptation=selected_adaptation_for_setup(
                    component, harness_id=setup.harness_id, assessments=assessments
                ),
            )
        )
    return members


def alignment_state(
    *,
    member_digest: str | None,
    baseline_digest: str | None,
    member_accessible: bool,
    authorized: bool,
) -> str:
    """Compute family alignment for one exact version pair."""
    if not member_accessible:
        return "missing" if authorized else "unknown"
    if not member_digest or not baseline_digest:
        return "unknown"
    return "aligned" if member_digest == baseline_digest else "diverged"


def owner_target_gaps(matrix: TargetMatrix) -> list[OwnerTargetGap]:
    """Owner-safe coverage diagnostics. No foreign evidence or storage keys."""
    gaps: list[OwnerTargetGap] = []
    for row in matrix.exact:
        if row.assessment_state == "verified":
            continue
        action = {
            "not_verified": "submit_target_assessment",
            "stale": "refresh_target_assessment",
            "failed": "fix_target_and_resubmit",
        }.get(row.assessment_state, "submit_target_assessment")
        gaps.append(
            OwnerTargetGap(
                harness_id=row.harness_id,
                scope=row.scope,
                state=row.assessment_state,
                reason_code=None,
                next_action=action,
            )
        )
    for row in matrix.claimed_portable:
        gaps.append(
            OwnerTargetGap(
                harness_id=row.harness_id,
                scope=None,
                state="not_verified",
                reason_code="claim_only",
                next_action="publish_exact_adaptation",
                claim_id=row.claim_id,
                expires_at=row.expires_at,
            )
        )
    return gaps


def stale_if_expired(state: str, expires_at: datetime | None, *, now: datetime) -> AssessmentState:
    """Effective stale is calculated at read time."""
    if state == "verified" and expires_at is not None and expires_at <= now.astimezone(UTC):
        return "stale"
    if state in {"not_verified", "verified", "failed", "stale"}:
        return state  # type: ignore[return-value]
    return "not_verified"
