"""Technology intent: grow the registry from detection evidence, in-process.

Three actions share one drain:

- `unmapped` runs `project detect` for the given root and reports the
  coordinates the effective mapping cannot resolve — the local review queue,
  plus the organization's server-side queue when a session exists.
- `publish-mapping` writes one immutable organization snapshot, either from an
  explicit entries document or from the bundled seed table.
- `resolve` executes a decision list against the review queue: propose a
  candidate, or apply entries through one derived snapshot — creating the
  technologies and categories the decisions name.

All delegate to `application.project_technology`, so the task can never
disagree with the CLI about what a coordinate or a snapshot means.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import ValidationError

from ai_stp_cli.application import project_technology
from ai_stp_cli.errors import CliFailure, field_issues
from ai_stp_contracts.cli.tasks import TaskQuestion, TaskTechnologyDecision, TaskTechnologyOutcome
from ai_stp_foundation.canonical import JsonValue


@dataclass(frozen=True)
class DrainResult:
    outcome: TaskTechnologyOutcome | None = None
    questions: tuple[TaskQuestion, ...] = ()
    child_operation_ids: tuple[str, ...] = ()
    facts: dict[str, JsonValue] | None = None
    advance: bool = False


_ACTIONS = ("unmapped", "publish-mapping", "resolve")


def drain(facts: Mapping[str, JsonValue], *, task_id: str) -> DrainResult:
    """Advance the technology intent until a boundary."""
    action = facts.get("action")
    if not isinstance(action, str) or action not in _ACTIONS:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="action",
                    prompt="What should this task do?",
                    value_type="string",
                    choices=list(_ACTIONS),
                    recommended="unmapped",
                    why=(
                        "unmapped reports the coordinates a scan cannot resolve; "
                        "publish-mapping writes one immutable organization snapshot; "
                        "resolve applies a decision list to the review queue."
                    ),
                    actor="external",
                ),
            )
        )
    if action == "unmapped":
        return _drain_unmapped(facts)
    if action == "resolve":
        return _drain_resolve(facts, task_id=task_id)
    return _drain_publish_mapping(facts, task_id=task_id)


def _drain_unmapped(facts: Mapping[str, JsonValue]) -> DrainResult:
    root = facts.get("project_root")
    if not isinstance(root, str) or not root.strip():
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="project-root",
                    prompt="Which project root should be scanned?",
                    value_type="string",
                    choices=[],
                    why="Detection reads one bounded root; the task does not guess paths.",
                    actor="external",
                ),
            )
        )
    scope = facts.get("scope")
    organization = facts.get("organization_id")
    # `detect` resolves the organization from the project's cached link, never
    # from an option — the link is the only trusted binding.
    scan = project_technology.detect(
        {
            "root": root,
            "scope": scope if isinstance(scope, str) else "repository",
        }
    ).payload
    unmapped_parameters: dict[str, object] = {
        "project": scan.project_id,
        "scope": scope if isinstance(scope, str) else "repository",
    }
    if isinstance(organization, str) and organization.strip():
        unmapped_parameters["organization"] = organization
    view = project_technology.unmapped(unmapped_parameters).payload
    server_coordinates = []
    if isinstance(organization, str) and organization.strip():
        try:
            remote = project_technology.unmapped_remote({"organization": organization}).payload
            server_coordinates = list(remote.coordinates)
        except CliFailure:
            # No session or no access still leaves the local queue truthful.
            server_coordinates = []
    return DrainResult(
        outcome=TaskTechnologyOutcome(
            action="unmapped",
            project_id=scan.project_id,
            scan_id=scan.scan_id,
            scan_state=scan.state,
            organization_id=organization if isinstance(organization, str) else "",
            coordinates=view.coordinates,
            server_coordinates=server_coordinates,
        )
    )


def _drain_publish_mapping(facts: Mapping[str, JsonValue], *, task_id: str) -> DrainResult:
    missing = [
        name
        for name in ("organization_id", "mapping_version", "authorization_revision")
        if not isinstance(facts.get(name), (str, int)) or facts.get(name) in (None, "")
    ]
    if missing:
        return DrainResult(
            questions=tuple(
                TaskQuestion(
                    question_id=name.replace("_", "-"),
                    prompt=f"Value for `{name}` is required.",
                    value_type="string",
                    choices=[],
                    actor="external",
                )
                for name in missing
            )
        )
    seed = facts.get("seed") is True
    mapping_file = facts.get("mapping_file")
    parameters: dict[str, object] = {
        "organization": facts["organization_id"],
        "version": facts["mapping_version"],
        "authorization-revision": str(facts["authorization_revision"]),
        "idempotency-key": facts.get("idempotency_key")
        or f"task-{task_id}-mapping-{facts['mapping_version']}",
    }
    if seed:
        parameters["seed"] = True
    elif isinstance(mapping_file, str) and mapping_file.strip():
        parameters["entries"] = mapping_file
    else:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="mapping-source",
                    prompt="Publish the bundled seed table, or an entries document?",
                    value_type="string",
                    choices=["seed", "entries"],
                    recommended="seed",
                    why=(
                        "seed ships the curated bundled table; entries names a "
                        "JSON/YAML document of coordinate rows."
                    ),
                    actor="external",
                ),
            )
        )
    view = project_technology.mapping_publish(parameters).payload
    return DrainResult(
        outcome=TaskTechnologyOutcome(
            action="publish-mapping",
            organization_id=str(facts["organization_id"]),
            mapping_version=view.version,
            mapping_digest=view.digest,
        )
    )


def _drain_resolve(facts: Mapping[str, JsonValue], *, task_id: str) -> DrainResult:
    missing = [
        name
        for name in ("organization_id", "authorization_revision")
        if not isinstance(facts.get(name), (str, int)) or facts.get(name) in (None, "")
    ]
    raw = facts.get("decisions")
    if not isinstance(raw, list) or not raw:
        missing.append("decisions")
    if missing:
        return DrainResult(
            questions=tuple(
                TaskQuestion(
                    question_id=name.replace("_", "-"),
                    prompt=f"Value for `{name}` is required.",
                    value_type="string",
                    choices=[],
                    why=(
                        "decisions holds the review list: each row maps one "
                        "queued coordinate to a technology — existing or to "
                        "create — as propose or apply."
                        if name == "decisions"
                        else "resolve cannot guess it."
                    ),
                    actor="external",
                )
                for name in missing
            )
        )
    items = raw if isinstance(raw, list) else []
    try:
        decisions = [TaskTechnologyDecision.model_validate(item) for item in items]
    except ValidationError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a review decision does not match the contract",
            details={"errors": field_issues(error)},
        ) from error
    # An optional root refreshes the local scan first so the outcome reports
    # the queue the caller just saw, not a stale one.
    project_id = ""
    scan_id = ""
    scan_state = None
    root = facts.get("project_root")
    if isinstance(root, str) and root.strip():
        scan = project_technology.detect(
            {
                "root": root,
                "scope": facts.get("scope")
                if isinstance(facts.get("scope"), str)
                else "repository",
            }
        ).payload
        project_id, scan_id, scan_state = scan.project_id, scan.scan_id, scan.state
    raw_revision = facts["authorization_revision"]
    authorization_revision = int(raw_revision) if isinstance(raw_revision, (int, str)) else 0
    raw_base = facts.get("base_version")
    raw_version = facts.get("mapping_version")
    outcome = project_technology.resolve_decisions(
        organization=str(facts["organization_id"]),
        decisions=decisions,
        authorization_revision=authorization_revision,
        idempotency_key=str(facts.get("idempotency_key") or f"task-{task_id}-resolve"),
        base_version=raw_base if isinstance(raw_base, str) else None,
        mapping_version=raw_version if isinstance(raw_version, str) else None,
    )
    return DrainResult(
        outcome=outcome.model_copy(
            update={
                "project_id": project_id,
                "scan_id": scan_id,
                "scan_state": scan_state,
            }
        )
    )
