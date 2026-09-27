"""Publish intent: no-binding publication plan, artifact PUT, confirm. Receipt ≠ readable."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ai_stp_cli.application import account as account_service
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.machine_help import PublicationPlanView, TaskPublishOutcome, TaskQuestion
from ai_stp_contracts.publication import (
    PLAN_STATE_PUBLISHED,
    PLAN_STATES_IN_PROGRESS,
    PLAN_STATES_REFUSED,
)
from ai_stp_foundation.canonical import JsonValue

_VISIBILITY = ("private", "public")


@dataclass(frozen=True)
class DrainResult:
    outcome: TaskPublishOutcome | None = None
    questions: tuple[TaskQuestion, ...] = ()
    child_operation_ids: tuple[str, ...] = ()
    facts: dict[str, JsonValue] | None = None
    advance: bool = False


def publication_status(plan_id: str) -> PublicationPlanView:
    """Read an existing plan without creating another publication attempt."""
    from ai_stp_cli.application import publication as publication_service

    return publication_service.show({"plan-id": plan_id}).payload


def plan_publication(parameters: Mapping[str, object]) -> PublicationPlanView:
    """Create the distribution plan. Tests may stub this."""
    from ai_stp_cli.application import publication as publication_service

    return publication_service.plan(parameters).payload


def confirm_publication(*, plan_id: str, plan_hash: str) -> PublicationPlanView:
    """Confirm the exact plan under task authority. Tests may stub this."""
    from ai_stp_cli.application import publication as publication_service

    return publication_service.confirm(
        {
            "plan-id": plan_id,
            "plan-hash": plan_hash,
            "confirm": True,
            "idempotency-key": plan_id,
        }
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
    if previous is not None:
        if previous.object_id != object_id or previous.object_version != object_version:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the publication task no longer names its recorded object",
            )
        if previous.state in {"draft", "ready"}:
            current = confirm_publication(plan_id=previous.plan_id, plan_hash=previous.plan_hash)
        else:
            current = publication_status(previous.plan_id)
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
        current = planned
    if (
        current.stable_id != object_id
        or current.version != object_version
        or current.visibility != chosen_visibility
        or current.source_binding_id is not None
        or (
            previous is not None
            and (current.plan_id != previous.plan_id or current.plan_hash != previous.plan_hash)
        )
    ):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the publication plan changed after the task recorded it",
        )
    readable = current.state == PLAN_STATE_PUBLISHED
    waiting = current.state in PLAN_STATES_IN_PROGRESS - {"draft", "ready"}
    return DrainResult(
        outcome=TaskPublishOutcome(
            object_id=current.stable_id,
            object_version=current.version,
            visibility=current.visibility,
            source_binding_id=current.source_binding_id or "",
            plan_id=current.plan_id,
            plan_hash=current.plan_hash,
            state=current.state,
            readable=readable,
        ),
        advance=current.state in {"draft", "ready"},
        questions=(_processing_question(),) if waiting else (),
    )


def _processing_question() -> TaskQuestion:
    """The typed external wait while the platform worker decides.

    The accepted worker receipt does not establish catalog readability, so a
    still-validating member blocks the task rather than settling it.
    """
    return TaskQuestion(
        question_id="publication-processing",
        prompt="Publication is processing. Resume this task after the platform finishes.",
        value_type="string",
        choices=[],
        why="The accepted worker receipt does not establish catalog readability.",
        actor="external",
    )


def _drain_setup(
    stable_id: str, version: str, *, visibility: str, previous: TaskPublishOutcome | None
) -> DrainResult:
    from ai_stp_cli.application import setup_publication

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
    # The first member that has not reached published decides the task's
    # boundary: client-side work still owed resumes as planned, a worker-side
    # decision waits as a typed external question, and a final refusal settles
    # truthfully. A bounded poll alone must never mark the task completed.
    unfinished = next(
        (
            member
            for member in receipt.members
            if not member.already_published and member.state != PLAN_STATE_PUBLISHED
        ),
        None,
    )
    waiting = (
        unfinished is not None
        and unfinished.state not in {"draft", "ready"}
        and unfinished.state not in PLAN_STATES_REFUSED
        and unfinished.state != "blocked"
    )
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
        advance=unfinished is not None and unfinished.state in {"draft", "ready"},
        questions=(_processing_question(),) if waiting else (),
    )
