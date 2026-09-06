"""Deterministic setup evaluation planning and immutable local evidence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import component_passports, content, revisions, versions
from ai_stp_contracts.evaluation import (
    ComponentEvalPlan,
    ComponentEvalResult,
    EvalComponentCoordinate,
    EvaluationBudget,
    EvaluationCheck,
    EvaluationCheckResult,
    SetupEvalPlan,
    SetupEvalProfile,
    SetupEvalResult,
)
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports.envelope import verify_revision_id
from ai_stp_passports.versions import (
    COMPONENT_TYPES,
    ComponentType,
    ComponentVersionPassport,
    Permissions,
    SetupVersionPassport,
)

PROFILE_VERSION: Final[str] = "setup-eval/1"
RUNNER_VERSION: Final[str] = "ai-stp-local-static/1"
_STATIC_MESSAGE: Final[dict[bool, str]] = {
    True: "The declared deterministic assertion passed.",
    False: "At least one component lacks its type-specific declared static surface.",
}
_TYPES: Final[tuple[ComponentType, ...]] = COMPONENT_TYPES
_SURFACES: Final[dict[ComponentType, tuple[str, ...]]] = {
    "instruction": ("managed_paths",),
    "skill": ("managed_paths", "entry_points"),
    "mcp": ("native_ids", "entry_points"),
    "hook": ("native_ids", "managed_paths"),
    "command": ("native_ids", "entry_points"),
    "agent": ("native_ids", "entry_points"),
    "plugin": ("native_ids", "managed_paths"),
    "setting": ("native_ids", "managed_paths"),
    "cli": ("native_ids", "entry_points"),
}


@dataclass(frozen=True)
class _Loaded:
    coordinate: EvalComponentCoordinate

    #: The declared static surfaces `_SURFACES` names, read from either stored
    #: shape: a public passport's fields, or an adopted draft's facts.
    surfaces: dict[str, tuple[str, ...]]
    artifact: bytes


def reference_profile(
    component_types: tuple[ComponentType, ...] | None = None,
) -> SetupEvalProfile:
    """Return the closed reference profile for a setup or component subset."""
    selected = _TYPES if component_types is None else tuple(dict.fromkeys(component_types))
    if not selected:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "an evaluation profile needs a component type")
    checks: list[EvaluationCheck] = [
        EvaluationCheck(
            check_id="base.exact_coordinates",
            method="deterministic",
            runner="local_static",
            assertion="Every evaluated version and artifact matches its exact digest.",
            tolerance="Exact equality; no tolerance.",
            budget=EvaluationBudget(timeout_seconds=10, max_output_bytes=65536),
            isolation_requirements=["read-only registry"],
        )
    ]
    directions = {
        "instruction": "declared managed path and bounded context footprint",
        "skill": "declared trigger surface and workflow artifact",
        "mcp": "declared native server or entry point and bounded permissions",
        "hook": "declared lifecycle surface and failure boundary",
        "command": "declared invocation surface and exit contract",
        "agent": "declared delegation surface and tool boundary",
        "plugin": "declared plugin identity or managed root",
        "setting": "declared merge target and harness effect",
        "cli": "declared process entry point and exit contract",
    }
    for component_type in selected:
        checks.extend(
            (
                EvaluationCheck(
                    check_id=f"{component_type}.static_contract",
                    component_type=component_type,
                    method="deterministic",
                    runner="local_static",
                    assertion=directions[component_type],
                    tolerance="Every matching component must satisfy the declared static surface.",
                    budget=EvaluationBudget(timeout_seconds=10, max_output_bytes=65536),
                    isolation_requirements=["read-only artifact bytes"],
                ),
                EvaluationCheck(
                    check_id=f"{component_type}.functional_behavior",
                    component_type=component_type,
                    method="model_assisted",
                    runner="model",
                    assertion="Evaluate functional behavior in the exact setup context.",
                    tolerance="No default tolerance; the author must declare a task oracle.",
                    budget=EvaluationBudget(timeout_seconds=300, max_output_bytes=262144),
                    isolation_requirements=["isolated runner", "explicit model credentials"],
                ),
                EvaluationCheck(
                    check_id=f"{component_type}.human_review",
                    component_type=component_type,
                    method="human_review",
                    runner="human",
                    assertion="Review intent, limitations, and residual risk.",
                    tolerance="A named reviewer records an explicit decision.",
                    budget=EvaluationBudget(timeout_seconds=3600, max_output_bytes=65536),
                    isolation_requirements=["reviewer identity"],
                ),
            )
        )
    scope = "component" if len(selected) == 1 else "setup"
    first_type = selected[0]
    return SetupEvalProfile(
        profile_id="ai-stp.reference.all-types"
        if len(selected) > 1
        else f"ai-stp.reference.{first_type}",
        scope=scope,
        component_types=list(selected),
        preconditions=[
            "The exact SetupVersion and every selected ComponentVersion are present locally.",
            "Artifact bytes match the digests in their immutable passports.",
        ],
        checks=checks,
        eval_permissions=Permissions(),
    )


def plan(
    connection: sqlite3.Connection,
    *,
    setup_id: str,
    setup_version: str,
    component_ids: tuple[str, ...],
    harness_version: str,
    provider_version: str,
    runner_version: str,
    at: str,
) -> SetupEvalPlan:
    """Bind the reference profile to one exact locally recorded setup graph."""
    setup_record = versions.held(connection, setup_id, setup_version)
    if setup_record is None:
        raise CliFailure("AI_STP_NOT_FOUND", "the exact setup version is not in the local registry")
    stored = revisions.get(connection, setup_record.revision_id)
    if stored is None:
        raise CliFailure("AI_STP_CONFLICT", "the setup version points to a missing passport")
    try:
        setup = SetupVersionPassport.model_validate(stored.envelope.model_dump(mode="json"))
    except ValueError as error:
        raise CliFailure("AI_STP_CONFLICT", "the recorded setup passport is invalid") from error
    if not verify_revision_id(setup) or setup_record.passport_digest != _passport_digest(setup):
        raise CliFailure("AI_STP_CONFLICT", "the setup passport no longer matches its exact digest")
    content.get(connection, setup.artifact.digest)
    wanted = set(component_ids)
    if len(wanted) != len(component_ids):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "component ids in an eval subset must be unique"
        )
    available = {item.stable_id for item in setup.components}
    if wanted - available:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "an evaluation subset names a component outside the exact setup graph",
            details={"unknown": ",".join(sorted(wanted - available))},
        )
    selected_refs = [item for item in setup.components if not wanted or item.stable_id in wanted]
    loaded = tuple(
        item
        for ref in selected_refs
        for item in _components(
            connection,
            ref.stable_id,
            ref.version,
            ref.passport_digest,
            harness_id=setup.harness_id,
        )
    )
    if not loaded:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the setup graph has no adaptation for its own harness",
            details={"setup_id": setup.stable_id, "harness_id": setup.harness_id},
        )
    types = cast(
        tuple[ComponentType, ...],
        tuple(dict.fromkeys(item.coordinate.component_type for item in loaded)),
    )
    profile = reference_profile(types).model_copy(
        update={"scope": "setup" if not wanted else "component" if len(loaded) == 1 else "subset"}
    )
    body: dict[str, JsonValue] = {
        "schema_version": 1,
        "profile": cast(JsonValue, profile.model_dump(mode="json")),
        "setup_id": setup.stable_id,
        "setup_version": setup.version,
        "setup_passport_digest": setup_record.passport_digest,
        "setup_artifact_digest": setup.artifact.digest,
        "harness_id": setup.harness_id,
        "harness_version": harness_version,
        "provider_version": provider_version,
        "runner_version": runner_version,
        "components": cast(JsonValue, [item.coordinate.model_dump(mode="json") for item in loaded]),
        "planned_at": at,
    }
    digest = digest_bytes("ai-stp:setup-eval-plan:v1", canonize(body))
    result = SetupEvalPlan.model_validate(
        {
            "plan_id": f"eval_plan_{digest.removeprefix('sha256:')[:24]}",
            "plan_digest": digest,
            **body,
        }
    )
    connection.execute(
        "INSERT INTO eval_plan "
        "(plan_id, plan_digest, document_json, created_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(plan_digest) DO NOTHING",
        (result.plan_id, result.plan_digest, result.model_dump_json(), at),
    )
    return result


def component_plan(
    connection: sqlite3.Connection,
    *,
    stable_id: str,
    version: str,
    harness_version: str,
    provider_version: str,
    runner_version: str,
    at: str,
) -> ComponentEvalPlan:
    """Bind the reference profile to every advertised adaptation of one version."""
    recorded = versions.held(connection, stable_id, version)
    if recorded is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the exact component version is not in the local registry",
            details={"stable_id": stable_id, "version": version},
        )
    loaded = _components(connection, stable_id, version, recorded.passport_digest)
    if not loaded:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the component version has no adaptations to evaluate",
            details={"stable_id": stable_id, "version": version},
        )
    types = cast(
        tuple[ComponentType, ...],
        tuple(dict.fromkeys(item.coordinate.component_type for item in loaded)),
    )
    profile = reference_profile(types).model_copy(update={"scope": "component"})
    body: dict[str, JsonValue] = {
        "schema_version": 1,
        "profile": cast(JsonValue, profile.model_dump(mode="json")),
        "stable_id": stable_id,
        "version": version,
        "passport_digest": recorded.passport_digest,
        "artifact_digest": loaded[0].coordinate.artifact_digest,
        "harness_version": harness_version,
        "provider_version": provider_version,
        "runner_version": runner_version,
        "components": cast(JsonValue, [item.coordinate.model_dump(mode="json") for item in loaded]),
        "planned_at": at,
    }
    digest = digest_bytes("ai-stp:component-eval-plan:v1", canonize(body))
    result = ComponentEvalPlan.model_validate(
        {
            "plan_id": f"eval_plan_{digest.removeprefix('sha256:')[:24]}",
            "plan_digest": digest,
            **body,
        }
    )
    connection.execute(
        "INSERT INTO eval_plan "
        "(plan_id, plan_digest, document_json, created_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(plan_digest) DO NOTHING",
        (result.plan_id, result.plan_digest, result.model_dump_json(), at),
    )
    return result


def run(
    connection: sqlite3.Connection, plan_id: str, expected_digest: str, *, at: str
) -> SetupEvalResult:
    """Run local-static checks for one confirmed setup evaluation plan."""
    existing = _existing_result(connection, plan_id)
    if existing is not None:
        if not isinstance(existing, SetupEvalResult):
            raise CliFailure(
                "AI_STP_CONFLICT", "the stored evaluation run is not a setup evaluation"
            )
        if existing.plan.plan_digest != expected_digest:
            raise CliFailure(
                "AI_STP_CONFLICT", "the eval plan digest differs from the completed run"
            )
        return existing
    selected = show_plan(connection, plan_id)
    if selected.plan_digest != expected_digest:
        raise CliFailure("AI_STP_PRECONDITION_FAILED", "the eval plan digest changed before run")
    result = _persist_result(
        connection,
        plan_id=plan_id,
        selected=selected,
        domain="ai-stp:setup-eval-result:v1",
        model=SetupEvalResult,
        at=at,
    )
    assert isinstance(result, SetupEvalResult)
    return result


def run_component(
    connection: sqlite3.Connection, plan_id: str, expected_digest: str, *, at: str
) -> ComponentEvalResult:
    """Run local-static checks for every advertised adaptation of one version."""
    existing = _existing_result(connection, plan_id)
    if existing is not None:
        if not isinstance(existing, ComponentEvalResult):
            raise CliFailure(
                "AI_STP_CONFLICT", "the stored evaluation run is not a component evaluation"
            )
        if existing.plan.plan_digest != expected_digest:
            raise CliFailure(
                "AI_STP_CONFLICT", "the eval plan digest differs from the completed run"
            )
        return existing
    selected = show_component_plan(connection, plan_id)
    if selected.plan_digest != expected_digest:
        raise CliFailure("AI_STP_PRECONDITION_FAILED", "the eval plan digest changed before run")
    result = _persist_result(
        connection,
        plan_id=plan_id,
        selected=selected,
        domain="ai-stp:component-eval-result:v1",
        model=ComponentEvalResult,
        at=at,
    )
    assert isinstance(result, ComponentEvalResult)
    return result


def show_plan(connection: sqlite3.Connection, plan_id: str) -> SetupEvalPlan:
    document = _plan_document(connection, plan_id)
    if "setup_id" not in document:
        raise CliFailure("AI_STP_CONFLICT", "the evaluation plan is not a setup evaluation")
    return SetupEvalPlan.model_validate_json(document)


def show_component_plan(connection: sqlite3.Connection, plan_id: str) -> ComponentEvalPlan:
    document = _plan_document(connection, plan_id)
    if "setup_id" in document:
        raise CliFailure("AI_STP_CONFLICT", "the evaluation plan is not a component evaluation")
    return ComponentEvalPlan.model_validate_json(document)


def show_result(
    connection: sqlite3.Connection, run_id: str
) -> SetupEvalResult | ComponentEvalResult:
    row = connection.execute(
        "SELECT document_json FROM eval_result WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None:
        raise CliFailure("AI_STP_NOT_FOUND", "the evaluation run does not exist")
    payload = str(row[0])
    if '"setup_id"' in payload:
        return SetupEvalResult.model_validate_json(payload)
    return ComponentEvalResult.model_validate_json(payload)


def _plan_document(connection: sqlite3.Connection, plan_id: str) -> str:
    row = connection.execute(
        "SELECT document_json FROM eval_plan WHERE plan_id = ?", (plan_id,)
    ).fetchone()
    if row is None:
        raise CliFailure("AI_STP_NOT_FOUND", "the evaluation plan does not exist")
    return str(row[0])


def _existing_result(
    connection: sqlite3.Connection, plan_id: str
) -> SetupEvalResult | ComponentEvalResult | None:
    row = connection.execute(
        "SELECT document_json FROM eval_result WHERE plan_id = ?", (plan_id,)
    ).fetchone()
    if row is None:
        return None
    payload = str(row[0])
    if '"setup_id"' in payload:
        return SetupEvalResult.model_validate_json(payload)
    return ComponentEvalResult.model_validate_json(payload)


def _persist_result(
    connection: sqlite3.Connection,
    *,
    plan_id: str,
    selected: SetupEvalPlan | ComponentEvalPlan,
    domain: str,
    model: type[SetupEvalResult] | type[ComponentEvalResult],
    at: str,
) -> SetupEvalResult | ComponentEvalResult:
    loaded = tuple(
        item
        for coordinate in selected.components
        for item in _components(
            connection,
            coordinate.stable_id,
            coordinate.version,
            coordinate.passport_digest,
            adaptation_id=coordinate.adaptation_id,
        )
    )
    checks = _execute_checks(selected.profile, loaded)
    aggregate = (
        "failed"
        if any(item.status == "failed" for item in checks)
        else "degraded"
        if any(item.status != "passed" for item in checks)
        else "passed"
    )
    body: dict[str, JsonValue] = {
        "schema_version": 1,
        "plan": cast(JsonValue, selected.model_dump(mode="json")),
        "status": aggregate,
        "executed_at": at,
        "checks": cast(JsonValue, [item.model_dump(mode="json") for item in checks]),
        "immutable_published_bytes_changed": False,
        "provider_permissions_used": False,
    }
    digest = digest_bytes(domain, canonize(body))
    result = model.model_validate(
        {
            "run_id": f"eval_run_{digest.removeprefix('sha256:')[:24]}",
            "result_digest": digest,
            **body,
        }
    )
    connection.execute(
        "INSERT INTO eval_result (run_id, plan_id, result_digest, document_json, executed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (result.run_id, plan_id, result.result_digest, result.model_dump_json(), at),
    )
    return result


def _execute_checks(
    profile: SetupEvalProfile, loaded: tuple[_Loaded, ...]
) -> list[EvaluationCheckResult]:
    checks: list[EvaluationCheckResult] = []
    for check in profile.checks:
        matching = [
            item
            for item in loaded
            if check.component_type in {None, item.coordinate.component_type}
        ]
        if check.runner != "local_static":
            checks.append(
                EvaluationCheckResult(
                    check_id=check.check_id,
                    method=check.method,
                    runner=check.runner,
                    status="not_run",
                    message=f"Runner {check.runner!r} is not configured for this local run.",
                    component_ids=[item.coordinate.stable_id for item in matching],
                    adaptation_ids=[
                        item.coordinate.adaptation_id
                        for item in matching
                        if item.coordinate.adaptation_id
                    ],
                )
            )
            continue
        if check.component_type is None:
            passed = bool(matching)
            checks.append(
                EvaluationCheckResult(
                    check_id=check.check_id,
                    method=check.method,
                    runner=RUNNER_VERSION,
                    status="passed" if passed else "failed",
                    message=_STATIC_MESSAGE[passed],
                    component_ids=[item.coordinate.stable_id for item in matching],
                )
            )
            continue
        if not matching:
            checks.append(
                EvaluationCheckResult(
                    check_id=check.check_id,
                    method=check.method,
                    runner=RUNNER_VERSION,
                    status="failed",
                    message=_STATIC_MESSAGE[False],
                    component_ids=[],
                )
            )
            continue
        for item in matching:
            passed = _static_contract(item)
            checks.append(
                EvaluationCheckResult(
                    check_id=check.check_id,
                    method=check.method,
                    runner=RUNNER_VERSION,
                    status="passed" if passed else "failed",
                    message=_STATIC_MESSAGE[passed],
                    component_ids=[item.coordinate.stable_id],
                    adaptation_ids=(
                        [item.coordinate.adaptation_id] if item.coordinate.adaptation_id else []
                    ),
                )
            )
    return checks


def _components(
    connection: sqlite3.Connection,
    stable_id: str,
    version: str,
    expected: str,
    *,
    adaptation_id: str | None = None,
    harness_id: str | None = None,
) -> tuple[_Loaded, ...]:
    recorded = versions.held(connection, stable_id, version)
    if recorded is None or recorded.passport_digest != expected:
        raise CliFailure(
            "AI_STP_CONFLICT", "an exact setup component version is missing or changed"
        )
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None:
        raise CliFailure("AI_STP_CONFLICT", "a component version points to a missing passport")
    document = cast(JsonValue, stored.envelope.model_dump(mode="json"))
    if digest_bytes("ai-stp:passport:v1", canonize(document)) != expected:
        raise CliFailure(
            "AI_STP_CONFLICT", "a component passport no longer matches its exact digest"
        )
    # Two stored shapes, exactly as `impact.py` records: a first-party
    # component is a complete public passport and validates directly, an
    # adopted component is stored as the draft it was adopted into. The draft
    # used to be pushed through the *publication* profile here, which refused
    # every plain adopted component for fields the evaluation never reads
    # (`#66`); the declared surfaces are read from the draft's own facts, and
    # the digest above already proved the stored bytes are the recorded ones.
    try:
        passport: ComponentVersionPassport | None = ComponentVersionPassport.model_validate(
            document
        )
    except ValueError:
        passport = None
    if passport is None:
        kind, digest, surfaces = _draft_surfaces(
            stable_id, version, cast(dict[str, JsonValue], document)
        )
        artifact = content.get(connection, digest)
        return (
            _Loaded(
                EvalComponentCoordinate(
                    stable_id=stable_id,
                    version=version,
                    passport_digest=expected,
                    artifact_digest=digest,
                    component_type=kind,
                ),
                surfaces,
                artifact,
            ),
        )
    if not verify_revision_id(passport):
        raise CliFailure(
            "AI_STP_CONFLICT", "a component passport no longer matches its exact digest"
        )
    return _adaptations(
        connection, passport, stable_id, version, expected, adaptation_id, harness_id
    )


def _adaptations(
    connection: sqlite3.Connection,
    passport: ComponentVersionPassport,
    stable_id: str,
    version: str,
    expected: str,
    adaptation_id: str | None,
    harness_id: str | None,
) -> tuple[_Loaded, ...]:
    selected = [
        item
        for item in passport.adaptations
        if (adaptation_id is None or item.adaptation_id == adaptation_id)
        and (harness_id is None or item.harness_id == harness_id)
    ]
    if not selected:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "an evaluation coordinate names an adaptation that is not on this version",
            details={
                "stable_id": stable_id,
                "adaptation_id": adaptation_id or "",
                "harness_id": harness_id or "",
            },
        )
    loaded: list[_Loaded] = []
    for adaptation in selected:
        members = [member for scope in adaptation.scope_adaptations for member in scope.members]
        declared = {
            "managed_paths": tuple(member.path for member in members),
            "native_ids": tuple(native_id for member in members for native_id in member.native_ids),
            "entry_points": tuple(
                str(item) for item in (passport.model_extra or {}).get("entry_points", [])
            ),
        }
        surfaces = {field: declared[field] for field in _SURFACES[passport.component_type]}
        projection = adaptation.scope_adaptations[0].projection_artifact
        artifact = content.get(connection, projection.digest)
        loaded.append(
            _Loaded(
                EvalComponentCoordinate(
                    stable_id=stable_id,
                    version=version,
                    passport_digest=expected,
                    artifact_digest=projection.digest,
                    component_type=passport.component_type,
                    adaptation_id=adaptation.adaptation_id,
                    harness_id=adaptation.harness_id,
                    projection_digest=projection.digest,
                ),
                surfaces,
                artifact,
            )
        )
    return tuple(loaded)


def _draft_surfaces(
    stable_id: str, version: str, document: dict[str, JsonValue]
) -> tuple[ComponentType, str, dict[str, tuple[str, ...]]]:
    """An adopted draft's kind, content digest and declared static surfaces."""
    values = component_passports.declared_values(document)
    component_type = values.get("component_type")
    artifact_digest = values.get("content_digest")
    missing = ""
    if not isinstance(component_type, str) or component_type not in _TYPES:
        missing = "component_type"
    elif not isinstance(artifact_digest, str) or not artifact_digest:
        missing = "content_digest"
    if missing:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "a recorded component passport lacks a fact this evaluation needs",
            details={"stable_id": stable_id, "version": version, "field": missing},
            next_actions=[f"component passport show --id {stable_id} --json"],
        )
    kind = cast(ComponentType, component_type)
    return (
        kind,
        str(artifact_digest),
        {field: component_passports.names_of(values.get(field)) for field in _SURFACES[kind]},
    )


def _passport_digest(passport: ComponentVersionPassport | SetupVersionPassport) -> str:
    return digest_bytes(
        "ai-stp:passport:v1", canonize(cast(JsonValue, passport.model_dump(mode="json")))
    )


def _static_contract(item: _Loaded) -> bool:
    if not item.artifact:
        return False
    return any(
        bool(item.surfaces.get(field)) for field in _SURFACES[item.coordinate.component_type]
    )
