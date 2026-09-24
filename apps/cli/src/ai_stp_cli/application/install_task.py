"""Install intent: pin or one justified pick, then acquire/plan/approve/apply."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ai_stp_cli import identity
from ai_stp_cli.application import install as install_service
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import harnesses, passports, project_passport, revisions, versions
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.machine_help import InstallationView, TaskInstallOutcome, TaskQuestion
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.harnesses import HARNESS_IDS
from ai_stp_foundation.ids import is_valid_id
from ai_stp_foundation.versioning import parse_version

PREFERRED_POSTURE: Final[str] = "baseline"


@dataclass(frozen=True)
class SetupPin:
    setup_id: str
    setup_version: str
    why: str


@dataclass(frozen=True)
class DrainResult:
    outcome: TaskInstallOutcome | None = None
    questions: tuple[TaskQuestion, ...] = ()
    child_operation_ids: tuple[str, ...] = ()


def _allowed_permissions(facts: Mapping[str, JsonValue]) -> tuple[str, ...]:
    value = facts.get("allowed_permissions")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "install input is not valid",
            details={"field": "allowed_permissions"},
        )
    return tuple(str(item) for item in value)


def recommend_setup(harness_id: str) -> SetupPin | None:
    """One justified pin. Never a catalog page."""
    from ai_stp_contracts.first_party import versions
    from ai_stp_passports.versions import SetupVersionPassport

    matching = [
        item.passport
        for item in versions()
        if item.kind == "setup"
        and isinstance(item.passport, SetupVersionPassport)
        and item.passport.harness_id == harness_id
    ]
    if not matching:
        return None
    chosen = next((item for item in matching if item.posture == PREFERRED_POSTURE), matching[0])
    posture = chosen.posture or PREFERRED_POSTURE
    return SetupPin(
        setup_id=chosen.stable_id,
        setup_version=chosen.version,
        why=f"First-party {posture} setup for {harness_id}.",
    )


def acquire_pin(setup_id: str, setup_version: str) -> None:
    """Use an exact owner-local setup, otherwise acquire the published graph."""
    from ai_stp_cli.application import catalog as catalog_service

    with closing(open_registry(configured_path(), create=True)) as connection:
        held = versions.held(connection, setup_id, setup_version)
        stored = revisions.get(connection, held.revision_id) if held is not None else None
        if (
            stored is not None
            and stored.envelope.kind == "setup"
            and stored.envelope.owner_id == passports.owner().account_id
        ):
            return
    catalog_service.acquire({"id": setup_id, "version": setup_version})


def ensure_local_context(root: Path) -> None:
    """Mint developer, device, and project passports if missing. Idempotent."""
    current, _warning = identity.load_or_create()
    with closing(open_registry(configured_path(), create=True)) as connection:
        passports.init_developer(connection, device_id=current.device_id)
        passports.ensure_device(connection, device_id=current.device_id)
        found = project_passport.scan(connection, root)
        project_passport.record(connection, found, device_id=current.device_id)


def harness_target(harness_id: str) -> Path:
    """Catalogued user-global config root. Creates the directory if missing."""
    detector = next(item for item in harnesses.DETECTORS if item.harness_id == harness_id)
    root = harnesses.config_root(detector)
    root.mkdir(parents=True, exist_ok=True)
    return root


def is_harness_config_root(root: Path) -> bool:
    """True when `root` is a catalogued harness config directory or inside one."""
    held = root.expanduser().resolve()
    return any(
        held == target or held.is_relative_to(target)
        for target in (
            harnesses.config_root(detector).resolve() for detector in harnesses.DETECTORS
        )
    )


def project_root_question(value: object, *, prompt: str, why: str) -> TaskQuestion | None:
    """Human question when the value is missing, relative, or a harness config root."""
    if (
        isinstance(value, str)
        and Path(value).is_absolute()
        and not is_harness_config_root(Path(value))
    ):
        return None
    cwd = Path.cwd()
    recommended = str(cwd) if cwd.is_absolute() and (cwd / ".git").is_dir() else ""
    held_why = (
        "A harness config directory is not a project root."
        if isinstance(value, str) and Path(value).is_absolute()
        else why
    )
    return TaskQuestion(
        question_id="project-root",
        prompt=prompt,
        value_type="string",
        choices=[recommended] if recommended else [],
        recommended=recommended,
        why=held_why,
        actor="human",
    )


def advance_held(operation_id: str) -> InstallationView:
    """Finish an existing operation. Never plan a second one."""
    try:
        return install_service.resume({"operation": operation_id}).payload
    except CliFailure as error:
        if error.code != "AI_STP_PRECONDITION_FAILED":
            raise
        return install_service.apply({"operation": operation_id}).payload


def drain(
    facts: Mapping[str, JsonValue],
    *,
    held_operation_ids: tuple[str, ...] = (),
    persist_operation: Callable[[str], None] | None = None,
) -> DrainResult:
    """Advance install until a boundary. Never shells out to `ai-stp`."""
    harness = facts.get("harness_id")
    if not isinstance(harness, str) or harness not in HARNESS_IDS:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="harness-id",
                    prompt="Which harness should receive this setup?",
                    value_type="string",
                    choices=sorted(HARNESS_IDS),
                    why="Install binds one harness target.",
                    actor="human",
                ),
            )
        )
    setup_id = facts.get("setup_id")
    setup_version = facts.get("setup_version")
    if not isinstance(setup_id, str) or not isinstance(setup_version, str):
        pin = recommend_setup(harness) if setup_id is None and setup_version is None else None
        if pin is None:
            return DrainResult(
                questions=(
                    TaskQuestion(
                        question_id="setup-ref",
                        prompt="Which exact setup should be installed? Answer as setup_id@X.Y.",
                        value_type="string",
                        choices=[],
                        why="The CLI installs one pin. It will not quiz the catalog.",
                        actor="human",
                    ),
                )
            )
        setup_id = pin.setup_id
        setup_version = pin.setup_version
    if not is_valid_id(setup_id, "setup"):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "install input is not valid",
            details={"field": "setup_id"},
        )
    try:
        parse_version(setup_version)
    except ValueError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "install input is not valid",
            details={"field": "setup_version"},
        ) from error
    question = project_root_question(
        facts.get("project_root"),
        prompt="Absolute project directory for this install?",
        why="Unsupported project-local must not silently become global.",
    )
    if question is not None:
        return DrainResult(questions=(question,))
    project_root = str(facts.get("project_root"))
    ensure_local_context(Path(project_root))
    held = next((item for item in held_operation_ids if is_valid_id(item, "operation")), None)
    if held is not None:
        view = advance_held(held)
        return DrainResult(
            outcome=TaskInstallOutcome(
                harness_id=harness,  # pyright: ignore[reportArgumentType]
                setup_id=setup_id,
                setup_version=setup_version,
                operation_id=view.operation_id,
                state=view.state,
                verified=view.state == "verified",
            ),
            child_operation_ids=(view.operation_id,),
        )
    acquire_pin(setup_id, setup_version)
    planned = install_service.plan(
        {
            "setup": f"{setup_id}@{setup_version}",
            "project": project_root,
            "harness": harness,
            "target": str(harness_target(harness)),
            "allow-permission": _allowed_permissions(facts),
        }
    )
    if persist_operation is not None:
        persist_operation(planned.payload.operation_id)
    approved = install_service.approve(
        {
            "operation": planned.payload.operation_id,
            "plan-digest": planned.payload.plan_digest,
        }
    )
    applied = install_service.apply({"operation": approved.payload.operation_id})
    view = applied.payload
    return DrainResult(
        outcome=TaskInstallOutcome(
            harness_id=harness,  # pyright: ignore[reportArgumentType]
            setup_id=setup_id,
            setup_version=setup_version,
            operation_id=view.operation_id,
            state=view.state,
            verified=view.state == "verified",
        ),
        child_operation_ids=(view.operation_id,),
    )
