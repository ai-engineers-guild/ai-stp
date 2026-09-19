"""Switch intent: restore last user working config. Never kill the caller."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from ai_stp_cli.application import install as install_service
from ai_stp_cli.application.install_task import project_root_question
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation, preserved_setups, project_passport
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.machine_help import InstallationView, TaskQuestion, TaskSwitchOutcome
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.harnesses import HARNESS_IDS


@dataclass(frozen=True)
class DrainResult:
    outcome: TaskSwitchOutcome | None = None
    questions: tuple[TaskQuestion, ...] = ()
    child_operation_ids: tuple[str, ...] = ()
    facts: dict[str, JsonValue] | None = None


def resolve_saved(
    *,
    harness_id: str,
    project_root: str,
    preserved_setup_id: str | None,
) -> preserved_setups.PreservedSetup:
    """Last user working config for this target. Never an upstream catalog pin."""
    root = Path(project_root).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve()
    with closing(open_registry(configured_path(), create=True)) as connection:
        if preserved_setup_id:
            saved = preserved_setups.held(connection, preserved_setup_id)
            if saved is None:
                raise CliFailure(
                    "AI_STP_NOT_FOUND",
                    "the preserved setup is not held by this registry",
                    details={"preserved_setup_id": preserved_setup_id},
                )
            _project_id, saved_harness = installation.target_pair(saved.target_id)
            if saved_harness != harness_id:
                raise CliFailure(
                    "AI_STP_CONFLICT",
                    "that preserved setup belongs to a different harness",
                    details={"harness_id": harness_id, "preserved_setup_id": preserved_setup_id},
                )
            return saved
        project_id = project_passport.stable_id_for(connection, root)
        if project_id is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "no preserved user setup for this target",
                details={"harness_id": harness_id, "project_root": str(root)},
            )
        saved = preserved_setups.latest_for(
            connection, installation.target_identity(project_id, harness_id)
        )
        if saved is None:
            raise CliFailure(
                "AI_STP_NOT_FOUND",
                "no preserved user setup for this target",
                details={"harness_id": harness_id, "project_root": str(root)},
            )
        return saved


def capture_drift(saved: preserved_setups.PreservedSetup) -> str:
    """Preserve current native state as a named leftover before restore."""
    project_id, harness_id = installation.target_pair(saved.target_id)
    applied = _plan_approve_apply(
        {
            "action": "backup",
            "protocol-version": 3,
            "project": project_id,
            "harness": harness_id,
            "target": saved.provider_target,
            "scope": saved.target_scope,
        }
    )
    return applied.preserved_setup_id or ""


def restore(saved: preserved_setups.PreservedSetup) -> InstallationView:
    """Restore the exact retained native snapshot through the provider."""
    project_id, harness_id = installation.target_pair(saved.target_id)
    return _plan_approve_apply(
        {
            "preserved-setup": saved.stable_id,
            "action": "rollback",
            "protocol-version": 3,
            "project": project_id,
            "harness": harness_id,
            "target": saved.provider_target,
            "scope": saved.target_scope,
            "backup-ref": saved.backup_ref,
        }
    )


def drain(facts: Mapping[str, JsonValue]) -> DrainResult:
    """Advance switch until a boundary. Never shells out to `ai-stp`. Never kills."""
    harness = facts.get("harness_id")
    if not isinstance(harness, str) or harness not in HARNESS_IDS:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="harness-id",
                    prompt="Which harness should return to the last working user config?",
                    value_type="string",
                    choices=sorted(HARNESS_IDS),
                    why="Switch restores one harness target.",
                    actor="human",
                ),
            )
        )
    question = project_root_question(
        facts.get("project_root"),
        prompt=(
            "Which absolute project directory should switch restore? "
            "Not a harness config directory."
        ),
        why="A preserved setup is bound to one project target, not the harness home.",
    )
    if question is not None:
        return DrainResult(questions=(question,))
    project_root = str(facts.get("project_root"))
    named = facts.get("preserved_setup_id")
    saved = resolve_saved(
        harness_id=harness,
        project_root=project_root,
        preserved_setup_id=named if isinstance(named, str) and named else None,
    )
    leftover = facts.get("drift_preserved_setup_id")
    operation_id = facts.get("operation_id")
    state = facts.get("state")
    if isinstance(leftover, str) and isinstance(operation_id, str) and isinstance(state, str):
        leftover_id = leftover
        restore_operation = operation_id
        restore_state = state
    else:
        leftover_id = capture_drift(saved)
        view = restore(saved)
        leftover_id = leftover_id or (view.preserved_setup_id or "")
        restore_operation = view.operation_id
        restore_state = view.state
    reload_session = facts.get("reload_session")
    if not isinstance(reload_session, str) or not reload_session.strip():
        held: dict[str, JsonValue] = {
            "harness_id": harness,
            "project_root": project_root,
            "preserved_setup_id": saved.stable_id,
            "drift_preserved_setup_id": leftover_id,
            "operation_id": restore_operation,
            "state": restore_state,
        }
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="reload-session",
                    prompt=(
                        "Native files are written. Reload this harness session, "
                        "then answer done. This process was not restarted."
                    ),
                    value_type="string",
                    choices=["done"],
                    recommended="done",
                    why="The CLI never kills the caller and never claims the session loaded.",
                    actor="human",
                ),
            ),
            child_operation_ids=(restore_operation,),
            facts=held,
        )
    return DrainResult(
        outcome=TaskSwitchOutcome(
            harness_id=harness,  # pyright: ignore[reportArgumentType]
            project_root=project_root,
            preserved_setup_id=saved.stable_id,
            drift_preserved_setup_id=leftover_id,
            operation_id=restore_operation,
            state=restore_state,
            verified=restore_state == "verified",
        ),
        child_operation_ids=(restore_operation,),
    )


def _plan_approve_apply(parameters: Mapping[str, object]) -> InstallationView:
    planned = install_service.plan(parameters)
    approved = install_service.approve(
        {
            "operation": planned.payload.operation_id,
            "plan-digest": planned.payload.plan_digest,
        }
    )
    return install_service.apply({"operation": approved.payload.operation_id}).payload
