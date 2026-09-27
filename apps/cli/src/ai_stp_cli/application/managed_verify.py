"""Read-only verification of a managed target against authorized records.

`corporate assignment verify` answers one question for CI: does this
(project, harness) target still carry exactly the setup and components the
organization authorized and the provider verified? It compares three layers
of evidence — the local verification log, the cached HarnessBundle manifest,
and the live provider status — against the corporate assignment plan, and
classifies every difference. It never repairs, never applies, and never asks
a provider to write.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from ai_stp_cli.answer import Answer
from ai_stp_cli.application import install as install_service
from ai_stp_cli.cloud import corporate
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, installation, managed_diff, targets, versions
from ai_stp_cli.local.database import configured_path, open_readonly
from ai_stp_cli.provider import status as provider_status
from ai_stp_contracts.corporate import (
    CorporateAssignmentPlan,
    CorporateAssignmentPlanRequest,
    CorporatePlanMaterializedItem,
    PlanOutcome,
)
from ai_stp_contracts.machine_help import (
    ManagedVerification,
    ManagedVerificationItem,
    ShadowedSurface,
)
from ai_stp_foundation.envelope import Continuation
from ai_stp_foundation.timestamps import format_timestamp

#: Path evidence stays bounded even when a target is heavily drifted; the
#: classification already says what happened, and a CI gate does not need ten
#: thousand path names to act on it.
_MAX_PATH_ITEMS = 64

_Classification = Literal[
    "unchanged",
    "locally_modified",
    "missing",
    "extra",
    "unverifiable",
    "expected_change",
]

_PATH_CLASSIFICATION: dict[str, _Classification] = {
    "modified": "locally_modified",
    "deleted": "missing",
    "added": "extra",
}

#: Options the provider status observation reads. They are forwarded
#: explicitly rather than inside the whole parameter mapping, so a declared
#: option the observer never consults is visible in this file instead of a
#: secondhand hop through `install.py`.
_OBSERVATION_KEYS: Final[tuple[str, ...]] = (
    "provider",
    "provider-manifest",
    "protocol-version",
    "target",
    "unverified-provider",
)

_Verdict = Literal[
    "pass",
    "fail",
    "outdated",
    "revoked",
    "unsupported",
    "not_enrolled",
    "unverifiable",
]


def verify_managed(
    parameters: Mapping[str, object],
    *,
    endpoint_url: Endpoint,
    access_token: str,
    account_id: str,
) -> Answer[ManagedVerification]:
    """Verify one managed target; report a verdict, never change anything."""
    organization = _required(parameters, "organization")
    harness = _required(parameters, "harness")
    given_project = _required(parameters, "local-project")
    remote_project = _optional(parameters, "project")
    technology = _optional(parameters, "technology")
    offline = _flag(parameters, "offline")
    checked_at = format_timestamp(datetime.now(UTC))

    diagnostics: list[str] = []
    registry = configured_path()
    if not registry.exists():
        return Answer(
            ManagedVerification(
                status="not_enrolled",
                project_id=given_project,
                harness_id=harness,  # pyright: ignore[reportArgumentType]
                organization_id=organization,
                account_id=account_id,
                remote_project_id=remote_project or "",
                technology_id=technology or "",
                checked_at=checked_at,
                corporate="offline" if offline else "unavailable",
                diagnostics=["no local ai-stp registry; the target was never managed"],
            )
        )

    with closing(open_readonly(registry)) as connection:
        resolved = install_service._project_id(connection, given_project)  # pyright: ignore[reportPrivateUsage]
        history = targets.verified(connection, project_id=resolved, harness_id=harness)
        if not history:
            return Answer(
                ManagedVerification(
                    status="not_enrolled",
                    project_id=resolved,
                    harness_id=harness,  # pyright: ignore[reportArgumentType]
                    organization_id=organization,
                    account_id=account_id,
                    remote_project_id=remote_project or "",
                    technology_id=technology or "",
                    checked_at=checked_at,
                    corporate="offline" if offline else "unavailable",
                    diagnostics=[
                        "no provider-verified installation exists for this project and harness"
                    ],
                )
            )

        record = history[-1]
        held = installation.plan(connection, record.operation_id)
        overview: managed_diff.BundleOverview | None = None
        baseline = record
        baseline_plan = held
        if held.provider_target and held.bundle_artifact_digest:
            archive = cache.stored_raw_artifact(held.bundle_artifact_digest)
            if archive is not None:
                overview = _overview(archive, diagnostics)
            else:
                diagnostics.append("the verified bundle archive is not in the local cache")
        else:
            diagnostics.append("the verified installation record carries no managed evidence")

        # A later verified installation on the same provider target — possibly
        # another pair's — is the authorized baseline. Comparing against the
        # caller's older record alone would report an authorized upgrade as
        # tampering.
        if held.provider_target:
            newer = targets.verified_for_target(connection, provider_target=held.provider_target)
            if newer and newer[-1].operation_id != record.operation_id:
                candidate = installation.plan(connection, newer[-1].operation_id)
                if candidate.provider_target and candidate.bundle_artifact_digest:
                    candidate_archive = cache.stored_raw_artifact(candidate.bundle_artifact_digest)
                    if candidate_archive is not None:
                        candidate_overview = _overview(candidate_archive, diagnostics)
                        if candidate_overview is not None:
                            baseline = newer[-1]
                            baseline_plan = candidate
                            overview = candidate_overview

        changes: tuple[managed_diff.Change, ...] = ()
        observed_digest = ""
        shadowed: tuple[provider_status.ShadowedSurface, ...] = ()
        inspected = False
        if overview is not None:
            if baseline_plan.provider_target:
                try:
                    changes = managed_diff.compare(
                        Path(baseline_plan.provider_target), overview.manifest
                    )
                    inspected = True
                except CliFailure as error:
                    diagnostics.append(str(error))
                    overview = None
            else:
                diagnostics.append(
                    "the verified installation record names no provider target; "
                    "managed content cannot be inspected"
                )
        observation = {name: parameters[name] for name in _OBSERVATION_KEYS if parameters.get(name)}
        try:
            observed_digest, _evidence, shadowed = install_service._observe_target(  # pyright: ignore[reportPrivateUsage]
                connection, observation, resolved, harness
            )
        except CliFailure as error:
            diagnostics.append(f"the provider status observation is unavailable: {error}")
            observed_digest = ""
            shadowed = ()
        for surface in shadowed:
            diagnostics.append(
                f"unmanaged surface {surface.name!r} takes precedence over {surface.over!r}"
            )

        materialized = _materialized(connection, baseline_plan, overview)

    plan_lines: dict[tuple[str, str], PlanOutcome] = {}
    corporate_state = "evaluated"
    found: CorporateAssignmentPlan | None = None
    if offline:
        corporate_state = "offline"
    else:
        request = CorporateAssignmentPlanRequest(
            account_id=account_id,
            harness=harness,  # pyright: ignore[reportArgumentType]
            project_id=remote_project,
            technology_id=technology,
            materialized=materialized,
        )
        try:
            found = corporate.assignment_plan(endpoint_url, access_token, organization, request)
        except CliFailure:
            corporate_state = "unavailable"
            found = None
            diagnostics.append(
                "the corporate assignment layer could not be reached; "
                "the local verdict is reported without it"
            )
        else:
            plan_lines = {(line.object_kind, line.stable_id): line.outcome for line in found.items}

    expected_change = baseline.operation_id != record.operation_id
    items = _items(
        baseline_plan,
        overview,
        changes,
        inspected=inspected,
        expected_change=expected_change,
        plan_lines=plan_lines,
        baseline_operation=baseline.operation_id,
    )
    drift = (
        bool(changes)
        or bool(shadowed)
        or bool(observed_digest and observed_digest != baseline.target_digest)
    )
    if observed_digest and observed_digest != baseline.target_digest:
        diagnostics.append(
            "the provider target digest differs from the verified record; "
            "the target changed outside the managed installation path"
        )
    status = _status(
        inspected=inspected,
        drift=drift,
        corporate=corporate_state,
        plan_lines=plan_lines,
        setup_stable_id=(
            overview.setup_stable_id
            if overview is not None and overview.setup_stable_id
            else baseline_plan.setup_stable_id
        ),
    )
    remediation: tuple[Continuation, ...] = ()
    if status != "pass" and found is not None:
        remediation = _remediation(found, resolved, diagnostics)
    return Answer(
        ManagedVerification(
            status=status,
            project_id=resolved,
            harness_id=harness,  # pyright: ignore[reportArgumentType]
            organization_id=organization,
            account_id=account_id,
            remote_project_id=remote_project or "",
            technology_id=technology or "",
            target_id=held.target_id,
            operation_id=baseline.operation_id,
            verified_at=baseline.at,
            checked_at=checked_at,
            corporate=corporate_state,  # pyright: ignore[reportArgumentType]
            verified_target_digest=baseline.target_digest,
            observed_target_digest=observed_digest,
            shadowed_surfaces=[
                ShadowedSurface(name=surface.name, over=surface.over, effect=surface.effect)
                for surface in shadowed
            ],
            items=items,
            diagnostics=diagnostics,
        ),
        continuations=remediation,
    )


def _remediation(
    found: CorporateAssignmentPlan,
    project_id: str,
    diagnostics: list[str],
) -> tuple[Continuation, ...]:
    """The one install plan that makes the assigned set materialize.

    A shape that cannot bind to exactly one prepared exact SetupVersion is a
    policy problem, not an install step: the verdict names the conflict and
    its exact identities in a blocked continuation for the organization
    administrator instead of printing a command that could not run, or
    silently reporting no action against a requirement nothing could satisfy.
    """
    assigned = [item for item in found.items if item.state == "assigned"]
    setups = [item for item in assigned if item.object_kind == "setup"]
    components = [item for item in assigned if item.object_kind == "component"]

    def _policy(
        conflict: str,
        key: str,
        identities: list[str],
        sentence: str,
    ) -> tuple[Continuation, ...]:
        diagnostics.append(sentence)
        return (
            Continuation(
                kind="blocked",
                path=["corporate", "assignment"],
                arguments={
                    "conflict": conflict,
                    key: list(identities),
                },
                missing=["organization-administrator"],
                actor="human",
            ),
        )

    if len(setups) > 1:
        return _policy(
            "multiple-setup-assignments",
            "setups",
            sorted(f"{item.stable_id}@{item.version or 'unversioned'}" for item in setups),
            "more than one setup is assigned; an install binds exactly one "
            "baseline, so the organization must narrow the assignment",
        )
    if len(setups) == 0:
        if not components:
            return ()
        return _policy(
            "components-without-setup-baseline",
            "components",
            sorted(f"{item.stable_id}@{item.version or 'unversioned'}" for item in components),
            "standalone components install only alongside a prepared exact "
            "SetupVersion; the assignment carries no baseline to bind them to",
        )
    unversioned = sorted(item.stable_id for item in assigned if not item.version)
    if unversioned:
        return _policy(
            "unversioned-assignment",
            "items",
            unversioned,
            "assigned items without an exact version cannot pin a prepared graph",
        )
    setup = setups[0]
    return (
        Continuation(
            kind="advance",
            path=["install", "plan"],
            arguments={
                "setup": f"{setup.stable_id}@{setup.version}",
                "component": [f"{item.stable_id}@{item.version}" for item in components],
                "project": project_id,
            },
        ),
    )


def _overview(archive: Path, diagnostics: list[str]) -> managed_diff.BundleOverview | None:
    try:
        return managed_diff.bundle_overview(archive)
    except CliFailure as error:
        diagnostics.append(str(error))
        return None


def _materialized(
    connection: sqlite3.Connection,
    plan: installation.Plan,
    overview: managed_diff.BundleOverview | None,
) -> list[CorporatePlanMaterializedItem]:
    """The exact lines the verified baseline installed, as plan input."""
    items: list[CorporatePlanMaterializedItem] = []
    passport_digest = overview.setup_passport_digest if overview is not None else ""
    if not passport_digest:
        held_version = versions.held(connection, plan.setup_stable_id, plan.setup_version)
        if held_version is not None:
            passport_digest = held_version.passport_digest or ""
    items.append(
        CorporatePlanMaterializedItem(
            object_kind="setup",
            stable_id=plan.setup_stable_id,
            version=plan.setup_version,
            passport_digest=passport_digest or None,
        )
    )
    if overview is not None:
        items.extend(
            CorporatePlanMaterializedItem(
                object_kind="component",
                stable_id=binding.stable_id,
                version=binding.version,
                passport_digest=binding.passport_digest or None,
            )
            for binding in overview.components
        )
    return items


def _items(
    plan: installation.Plan,
    overview: managed_diff.BundleOverview | None,
    changes: tuple[managed_diff.Change, ...],
    *,
    inspected: bool,
    expected_change: bool,
    plan_lines: dict[tuple[str, str], PlanOutcome],
    baseline_operation: str,
) -> list[ManagedVerificationItem]:
    items: list[ManagedVerificationItem] = []

    if overview is None or not inspected:
        items.append(
            ManagedVerificationItem(
                subject="setup",
                stable_id=plan.setup_stable_id,
                version=plan.setup_version,
                passport_digest=(overview.setup_passport_digest if overview is not None else ""),
                classification="unverifiable",
                outcome=plan_lines.get(("setup", plan.setup_stable_id), ""),  # pyright: ignore[reportArgumentType]
                diagnostic="the managed content could not be compared against "
                "the verified bundle manifest",
            )
        )
        if overview is not None:
            for binding in overview.components:
                items.append(
                    ManagedVerificationItem(
                        subject="component",
                        stable_id=binding.stable_id,
                        component_kind=binding.component_kind,
                        version=binding.version,
                        passport_digest=binding.passport_digest,
                        classification="unverifiable",
                        outcome=plan_lines.get(("component", binding.stable_id), ""),  # pyright: ignore[reportArgumentType]
                    )
                )
        return items

    # The setup line is the whole managed surface: drift anywhere under a
    # managed root is drift of the installed setup, while component items
    # attribute it to their own member paths.
    items.append(
        ManagedVerificationItem(
            subject="setup",
            stable_id=overview.setup_stable_id or plan.setup_stable_id,
            version=overview.setup_version or plan.setup_version,
            passport_digest=overview.setup_passport_digest,
            classification=_line_classification(list(changes), expected_change),
            outcome=plan_lines.get(("setup", overview.setup_stable_id or plan.setup_stable_id), ""),  # pyright: ignore[reportArgumentType]
            diagnostic=(f"verified by operation {baseline_operation}" if expected_change else ""),
        )
    )
    for binding in overview.components:
        drifted = [change for change in changes if change.path in set(binding.member_paths)]
        items.append(
            ManagedVerificationItem(
                subject="component",
                stable_id=binding.stable_id,
                component_kind=binding.component_kind,
                version=binding.version,
                passport_digest=binding.passport_digest,
                classification=_line_classification(drifted, expected_change),
                outcome=plan_lines.get(("component", binding.stable_id), ""),  # pyright: ignore[reportArgumentType]
            )
        )
    for change in changes[:_MAX_PATH_ITEMS]:
        items.append(
            ManagedVerificationItem(
                subject="path",
                path=change.path,
                change=change.code,  # pyright: ignore[reportArgumentType]
                expected_digest=change.expected_digest,
                observed_digest=change.observed_digest,
                classification=_PATH_CLASSIFICATION.get(change.code, "unverifiable"),
            )
        )
    if len(changes) > _MAX_PATH_ITEMS:
        items.append(
            ManagedVerificationItem(
                subject="path",
                classification="unverifiable",
                diagnostic=f"{len(changes) - _MAX_PATH_ITEMS} further changed "
                "managed paths are omitted",
            )
        )
    return items


def _line_classification(
    drifted: list[managed_diff.Change], expected_change: bool
) -> _Classification:
    if any(change.code == "modified" for change in drifted):
        return "locally_modified"
    if any(change.code == "deleted" for change in drifted):
        return "missing"
    if any(change.code == "added" for change in drifted):
        return "extra"
    return "expected_change" if expected_change else "unchanged"


def _status(
    *,
    inspected: bool,
    drift: bool,
    corporate: str,
    plan_lines: dict[tuple[str, str], PlanOutcome],
    setup_stable_id: str,
) -> _Verdict:
    """One verdict: proven violations first, then policy states, then unknowns."""
    if drift:
        return "fail"
    if corporate == "evaluated":
        setup_outcome = plan_lines.get(("setup", setup_stable_id), "")
        outcomes = set(plan_lines.values())
        if setup_outcome == "unassigned":
            return "not_enrolled"
        if setup_outcome == "":
            # The materialized setup is always reported to the plan, so an
            # evaluated answer that says nothing about it is not a verdict to
            # pass on.
            return "unverifiable"
        if "revoked" in outcomes or "unassigned" in outcomes:
            return "revoked"
        if "unsupported" in outcomes:
            return "unsupported"
        if outcomes & {"outdated", "conflicting", "missing"}:
            return "outdated"
        if not inspected:
            return "unverifiable"
        return "pass"
    return "unverifiable"


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = parameters.get(name)
    if not isinstance(value, str) or not value:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option was not supplied",
            details={"option": f"--{name}"},
        )
    return value


def _optional(parameters: Mapping[str, object], name: str) -> str | None:
    value = parameters.get(name)
    return value if isinstance(value, str) and value else None


def _flag(parameters: Mapping[str, object], name: str) -> bool:
    return bool(parameters.get(name))
