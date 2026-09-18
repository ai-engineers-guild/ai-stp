"""Author intent: register a directory as one component and one setup identity."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ai_stp_cli import identity
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import passports, setup_author
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.machine_help import TaskAuthorOutcome, TaskQuestion
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.harnesses import HARNESS_IDS
from ai_stp_passports.versions import COMPONENT_TYPES, ComponentType


@dataclass(frozen=True)
class DrainResult:
    outcome: TaskAuthorOutcome | None = None
    questions: tuple[TaskQuestion, ...] = ()
    child_operation_ids: tuple[str, ...] = ()


def persist(
    *,
    directory: Path,
    harness_id: str,
    component_type: str,
    name: str,
    license_spdx: str,
) -> setup_author.AuthoredSetup:
    """Persist the authored identity. Tests may stub this."""
    current, _warning = identity.load_or_create()
    at = passports.moment()
    with closing(open_registry(configured_path(), create=True)) as connection:
        return setup_author.record(
            connection,
            directory=directory,
            harness_id=harness_id,
            component_type=component_type,
            name=name,
            license_spdx=license_spdx,
            publisher_id=passports.owner().account_id,
            device_id=current.device_id,
            at=at,
        )


def drain(facts: Mapping[str, JsonValue]) -> DrainResult:
    """Advance author until a boundary. Never shells out to `ai-stp`."""
    directory = _directory(facts)
    if directory is None:
        cwd = Path.cwd()
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="directory",
                    prompt="Which directory holds the component files?",
                    value_type="string",
                    choices=[],
                    recommended=str(cwd) if cwd.is_dir() else "",
                    why="Author registers one existing tree, not a catalog pin.",
                    actor="human",
                ),
            )
        )
    harness = facts.get("harness_id")
    if not isinstance(harness, str) or harness not in HARNESS_IDS:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="harness-id",
                    prompt="Which harness should host this component?",
                    value_type="string",
                    choices=sorted(HARNESS_IDS),
                    why="A setup belongs to one harness from creation.",
                    actor="human",
                ),
            )
        )
    kinds = setup_author.kinds_for(harness)
    wanted_type = facts.get("component_type")
    if isinstance(wanted_type, str) and wanted_type in COMPONENT_TYPES and wanted_type not in kinds:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "this harness has no native surface for that component type",
            details={"harness_id": harness, "component_type": wanted_type},
        )
    if not isinstance(wanted_type, str) or wanted_type not in kinds:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="component-type",
                    prompt="Which component kind is this directory?",
                    value_type="string",
                    choices=list(kinds),
                    why="Kinds are the closed COMPONENT_TYPES this harness can host.",
                    actor="human",
                ),
            )
        )
    name = facts.get("name")
    if not isinstance(name, str) or not name.strip():
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="name",
                    prompt="What is the component's short name?",
                    value_type="string",
                    choices=[],
                    recommended=directory.name,
                    why="The name is the native surface label.",
                    actor="human",
                ),
            )
        )
    license_spdx = facts.get("license_spdx")
    if not isinstance(license_spdx, str) or not license_spdx.strip():
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="license-spdx",
                    prompt="Which SPDX license identifier applies to these files?",
                    value_type="string",
                    choices=[],
                    recommended=setup_author.PRIVATE_LICENSE,
                    why="Unpublished drafts stay privately licensed until publish.",
                    actor="human",
                ),
            )
        )
    authored = persist(
        directory=directory,
        harness_id=harness,
        component_type=wanted_type,
        name=name.strip()[:160],
        license_spdx=license_spdx.strip(),
    )
    return DrainResult(
        outcome=TaskAuthorOutcome(
            harness_id=harness,
            directory=str(directory),
            component_type=cast(ComponentType, wanted_type),
            name=name.strip()[:160],
            component_id=authored.component_id,
            component_version=authored.component_version,
            setup_id=authored.setup_id,
            setup_version=authored.setup_version,
            minted=authored.minted,
        )
    )


def _directory(facts: Mapping[str, JsonValue]) -> Path | None:
    raw = facts.get("directory")
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw.strip()).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        resolved = path.resolve()
    except OSError:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that directory does not exist",
            details={"directory": raw},
        ) from None
    if not resolved.is_dir():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that directory does not exist",
            details={"directory": str(resolved)},
        )
    return resolved
