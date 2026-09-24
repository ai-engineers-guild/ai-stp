"""Publish intent: no-binding publication plan, artifact PUT, confirm. Receipt ≠ readable."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ai_stp_cli.application import account as account_service
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.machine_help import PublicationPlanView, TaskPublishOutcome, TaskQuestion
from ai_stp_contracts.publication import PLAN_STATE_PUBLISHED
from ai_stp_foundation.canonical import JsonValue

_VISIBILITY = ("private", "public")


@dataclass(frozen=True)
class DrainResult:
    outcome: TaskPublishOutcome | None = None
    questions: tuple[TaskQuestion, ...] = ()
    child_operation_ids: tuple[str, ...] = ()
    facts: dict[str, JsonValue] | None = None
    advance: bool = False


def plan_publication(parameters: Mapping[str, object]) -> PublicationPlanView:
    """Create the distribution plan. Tests may stub this."""
    from ai_stp_cli.application import publication as publication_service

    return publication_service.plan(parameters).payload


def confirm_publication(*, plan_id: str, plan_hash: str) -> PublicationPlanView:
    """Confirm the exact plan under task authority. Tests may stub this."""
    from ai_stp_cli.application import publication as publication_service

    return publication_service.confirm(
        {"plan-id": plan_id, "plan-hash": plan_hash, "confirm": True}
    ).payload


def drain(
    facts: Mapping[str, JsonValue], *, previous: TaskPublishOutcome | None = None
) -> DrainResult:
    """Advance publish until a boundary. Never shells out to `ai-stp`. Never invents git."""
    gate = account_service.ensure_session(facts)
    if isinstance(gate, account_service.DrainResult):
        return DrainResult(questions=gate.questions, facts=gate.facts)
    object_id = facts.get("object_id")
    if not isinstance(object_id, str) or not object_id.strip():
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="object-id",
                    prompt="Which local object identifier should be published?",
                    value_type="string",
                    choices=[],
                    why="Publish ships one exact local identity, not a GitHub repository.",
                    actor="human",
                ),
            )
        )
    object_version = facts.get("object_version")
    if not isinstance(object_version, str) or not object_version.strip():
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="object-version",
                    prompt="Which exact version of that object should be published?",
                    value_type="string",
                    choices=[],
                    why="Publication pins an exact version. latest is not a version.",
                    actor="human",
                ),
            )
        )
    visibility = facts.get("visibility")
    if visibility is None:
        chosen_visibility = "private"
    elif isinstance(visibility, str) and visibility in _VISIBILITY:
        chosen_visibility = visibility
    else:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="visibility",
                    prompt="Publish privately (default) or publicly?",
                    value_type="string",
                    choices=["private", "public"],
                    recommended="private",
                    why="New publications default to private. Publicity is a separate decision.",
                    actor="human",
                ),
            )
        )
    if object_id.startswith("setup_"):
        return _drain_setup(
            object_id, object_version, visibility=chosen_visibility, previous=previous
        )
    plan_id = facts.get("plan_id")
    plan_hash = facts.get("plan_hash")
    if isinstance(plan_id, str) and plan_id and isinstance(plan_hash, str) and plan_hash:
        confirmed = confirm_publication(plan_id=plan_id, plan_hash=plan_hash)
    else:
        parameters: dict[str, object] = {
            "id": object_id,
            "version": object_version,
            "visibility": chosen_visibility,
        }
        directory = facts.get("directory")
        if isinstance(directory, str) and directory:
            root = Path(directory).expanduser()
            if not root.is_absolute():
                root = Path.cwd() / root
            parameters["component-root"] = str(root.resolve())
        planned = plan_publication(parameters)
        if planned.source_binding_id is not None:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "publication provenance must be the local filesystem",
                details={"source_binding_id": planned.source_binding_id},
            )
        confirmed = confirm_publication(plan_id=planned.plan_id, plan_hash=planned.plan_hash)
    readable = confirmed.state == PLAN_STATE_PUBLISHED
    return DrainResult(
        outcome=TaskPublishOutcome(
            object_id=confirmed.stable_id,
            object_version=confirmed.version,
            visibility=confirmed.visibility,
            source_binding_id=confirmed.source_binding_id or "",
            plan_id=confirmed.plan_id,
            plan_hash=confirmed.plan_hash,
            state=confirmed.state,
            readable=readable,
        )
    )


def _drain_setup(
    stable_id: str, version: str, *, visibility: str, previous: TaskPublishOutcome | None
) -> DrainResult:
    from ai_stp_cli.commands import setup_publication

    held = previous.publication_set if previous is not None else None
    if held is None:
        receipt = setup_publication.plan(
            {"id": stable_id, "version": version, "visibility": visibility}
        ).payload
    else:
        receipt = setup_publication.confirm(
            {"set-digest": held.set_digest, "confirm": True}
        ).payload
    setup = next(member for member in receipt.members if member.role == "setup")
    return DrainResult(
        outcome=TaskPublishOutcome(
            object_id=receipt.setup_stable_id,
            object_version=receipt.setup_version,
            visibility=setup.visibility,
            plan_id=setup.plan_id,
            plan_hash=setup.plan_hash,
            state=receipt.state,
            readable=receipt.state == PLAN_STATE_PUBLISHED,
            publication_set=receipt,
        ),
        advance=held is None and receipt.state != PLAN_STATE_PUBLISHED,
    )
