"""Initialize the active harness instruction surface through the provider.

ai-stp never Python-opens harness finals. The provider optional operation
`patch_instruction_region` writes the marked section. Production looks up
the remembered chosen or configured provider only — never PATH discovery
and never `ensure_provider`. Until that provider declares the operation
and `instruction_section`, the task stays blocked.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import harness_catalog, harnesses
from ai_stp_cli.provider import protocol_v3
from ai_stp_contracts.machine_help import TaskInitializeOutcome, TaskQuestion
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.harnesses import HARNESS_IDS

PATCH_OPERATION: Final[protocol_v3.Operation] = protocol_v3.Operation.PATCH_INSTRUCTION_REGION
SECTION_BEGIN: Final[str] = ":::begin-ai-stp"
SECTION_END: Final[str] = ":::end-ai-stp"
MAX_SECTION_BYTES: Final[int] = 2048
MAX_SECTION_LINES: Final[int] = 40
ANTIGRAVITY_LIMITATION: Final[str] = "no_global_instruction"
DIRECTORY_RULE_NAME: Final[str] = "ai-stp.mdc"
_FILE_SURFACES: Final[tuple[str, ...]] = ("CLAUDE.md", "AGENTS.md")

SECTION_BODY: Final[str] = """Use ai-stp through the task engine, not 200 commands.

You run ai-stp yourself with your tools. Do not ask the human to paste commands.
1. Run `ai-stp task intents --json` and pick one shipped intent.
2. Call `ai-stp task start`. `actor` is a JSON field on the continuation,
   not who you are. Execute argv only when that field is `cli`.
   Do not insert continue when actor is human.
3. Relay blocked questions once. Do not choreograph plan/approve/apply.
4. Report payload verification, not envelope `ok` alone.
"""


@dataclass(frozen=True)
class PatchObservation:
    section_digest: str
    wrote: bool


@dataclass(frozen=True)
class DrainResult:
    outcome: TaskInitializeOutcome | None = None
    questions: tuple[TaskQuestion, ...] = ()


type ProviderOperations = Callable[[], frozenset[protocol_v3.Operation]]
type RegionPatcher = Callable[[str, str], PatchObservation]


def _object(value: JsonValue) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], value) if isinstance(value, dict) else {}


def bound_executable(harness_id: str) -> Path | None:
    """Chosen or configured provider for this harness. Does not acquire or discover."""
    from contextlib import closing

    from ai_stp_cli.local import provider_installations as installations
    from ai_stp_cli.local.database import configured_path, open_readonly
    from ai_stp_cli.provider.acquire import configured_path as configured_provider

    named = configured_provider(harness_id)
    if named:
        place = Path(named)
        return place if place.is_file() else None
    registry = configured_path()
    if not registry.is_file():
        return None
    with closing(open_readonly(registry)) as connection:
        held = installations.remembered(connection, harness_id)
    if held is None or held.source != installations.SOURCE_CHOSEN or not held.path:
        return None
    place = Path(held.path)
    return place if place.is_file() else None


def bound_capabilities(harness_id: str) -> protocol_v3.ProviderCapabilities | None:
    """provider-info of the bound executable. Missing or unreadable is unspoken."""
    from ai_stp_cli.provider.attested_bind import inspect_provider

    executable = bound_executable(harness_id)
    if executable is None:
        return None
    try:
        return inspect_provider(executable)
    except CliFailure:
        return None


def provider_operations() -> frozenset[protocol_v3.Operation]:
    """Hook for tests. Production drain reads `bound_capabilities` instead."""
    return frozenset()


def patch_via_provider(harness_id: str, section: str) -> PatchObservation:
    """Provider-owned region write. Sends `--instruction-section` only when declared."""
    capabilities = bound_capabilities(harness_id)
    if (
        capabilities is None
        or PATCH_OPERATION not in capabilities.operations
        or "instruction_section" not in capabilities.plan_request_fields
    ):
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the provider does not support the requested native operation",
            details={
                "harness_id": harness_id,
                "operation": PATCH_OPERATION.value,
                "section_bytes": str(len(section.encode("utf-8"))),
            },
        )
    return invoke_region_patch(harness_id, section, capabilities)


def invoke_region_patch(
    harness_id: str,
    section: str,
    capabilities: protocol_v3.ProviderCapabilities,
) -> PatchObservation:
    """plan-operation + apply-operation. Isolation refusals stay typed failures."""
    from datetime import UTC, datetime, timedelta

    from ai_stp_cli.local import cache
    from ai_stp_cli.provider import invocation, operation_v3, release
    from ai_stp_foundation.ids import new_id
    from ai_stp_foundation.timestamps import format_timestamp

    executable = bound_executable(harness_id)
    detector = next((item for item in harnesses.DETECTORS if item.harness_id == harness_id), None)
    if executable is None or detector is None:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the provider does not support the requested native operation",
            details={"harness_id": harness_id, "operation": PATCH_OPERATION.value},
        )
    root = harnesses.config_root(detector)
    root.mkdir(parents=True, exist_ok=True)
    invoke = invocation.provider_invoker(str(executable), str(root), protocol_v3.VERSION)
    expected_target_digest = str(_object(invoke("status", ())).get("target_digest", ""))
    if not expected_target_digest:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider does not report a target digest, so a plan cannot be bound to one",
        )
    operation_id = new_id("operation")
    expires_at = format_timestamp(datetime.now(UTC) + timedelta(seconds=900))
    release_digest = release.artifact_identity(executable)[0]
    arguments = operation_v3.plan_operation_arguments(
        operation=PATCH_OPERATION,
        release_digest=release_digest,
        operation_id=operation_id,
        expires_at=expires_at,
        accepted_request_fields=capabilities.plan_request_fields,
        instruction_section=section,
    )
    plan = operation_v3.require_plan(
        _object(invoke("plan-operation", arguments)),
        capabilities=capabilities,
        release_digest=release_digest,
        operation_id=operation_id,
        operation=PATCH_OPERATION,
        target=root,
        expected_target_digest=expected_target_digest,
        bundle=None,
        backup_ref=None,
        permission_profile=None,
        expires_at=expires_at,
    )
    plan_path = cache.store_provider_plan(plan.artifact, plan.digest)
    operation_v3.require_applied(
        _object(
            invoke(
                "apply-operation",
                (
                    "--plan",
                    str(plan_path),
                    "--plan-digest",
                    plan.digest,
                    "--provider-release-digest",
                    release_digest,
                ),
            )
        ),
        plan=plan,
        bundle=None,
    )
    desired = extract_section(section) or section
    return PatchObservation(
        section_digest=section_digest(desired),
        wrote=_region_wrote(plan.effects),
    )


def wrap_section(body: str = SECTION_BODY, *, harness_id: str | None = None) -> str:
    """Visible markers. HTML comments are refused — Claude strips them."""
    inner = f"{SECTION_BEGIN}\n{body.rstrip()}\n{SECTION_END}\n"
    layout = global_instruction(harness_id) if harness_id else None
    if layout is not None and layout.shape == "directory":
        text = (
            "---\n"
            "description: Drive ai-stp through `task intents` and the five task verbs.\n"
            "alwaysApply: true\n"
            "---\n\n"
            f"{inner}"
        )
    else:
        text = inner
    encoded = text.encode("utf-8")
    lines = text.splitlines()
    if len(encoded) > MAX_SECTION_BYTES or len(lines) > MAX_SECTION_LINES:
        raise ValueError("initialize section exceeds the frozen byte/line budget")
    if "<!--" in text or "-->" in text:
        raise ValueError("initialize section must not use HTML comments")
    updated, _wrote = patch_file_text("", text)
    return updated


def section_digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_section(existing: str) -> str | None:
    begin = existing.find(SECTION_BEGIN)
    end = existing.find(SECTION_END)
    if begin == -1 or end == -1 or end < begin:
        return None
    end_at = end + len(SECTION_END)
    if end_at < len(existing) and existing[end_at : end_at + 1] == "\n":
        end_at += 1
    return existing[begin:end_at]


def splice_section(existing: str, section: str) -> str:
    """Replace the marked region or append it. Preserve every other byte."""
    held = extract_section(existing)
    if held is None:
        if not existing:
            return section
        prefix = existing if existing.endswith("\n") else f"{existing}\n"
        return prefix + section
    begin = existing.find(SECTION_BEGIN)
    return existing[:begin] + section + existing[begin + len(held) :]


def patch_file_text(existing: str, section: str) -> tuple[str, bool]:
    """Pure region patch. Callers that write files live outside this module."""
    desired = extract_section(section) or section
    current = extract_section(existing)
    if current is not None and section_digest(current) == section_digest(desired):
        return existing, False
    if not existing:
        return section, True
    return splice_section(existing, desired), True


def _region_wrote(effects: tuple[str, ...]) -> bool:
    """Kernel always emits one effect line; empty would fail require_plan."""
    return any(item.startswith("patch instruction region at ") for item in effects)


def global_instruction(harness_id: str) -> harness_catalog.Layout | None:
    definition = harness_catalog.BY_ID.get(harness_id)
    if definition is None:
        return None
    if ANTIGRAVITY_LIMITATION in definition.gaps:
        return None
    candidates = [
        layout
        for layout in definition.layouts
        if layout.component_type == "instruction" and layout.scope == "global"
    ]
    for name in _FILE_SURFACES:
        for layout in candidates:
            if layout.shape == "file" and layout.relative == name:
                return layout
    files = [layout for layout in candidates if layout.shape == "file"]
    if files:
        return files[0]
    return candidates[0] if candidates else None


def surface_relative(harness_id: str) -> str:
    layout = global_instruction(harness_id)
    if layout is None:
        return ""
    if layout.shape == "directory":
        return f"{layout.relative}/{DIRECTORY_RULE_NAME}"
    return layout.relative


def instruction_path(harness_id: str, environment: Mapping[str, str] | None = None) -> Path | None:
    """Catalogued user-global path, including custom home overrides. Does not write."""
    relative = surface_relative(harness_id)
    if not relative:
        return None
    detector = next(
        (item for item in harnesses.DETECTORS if item.harness_id == harness_id),
        None,
    )
    if detector is None:
        return None
    held = dict(environment) if environment is not None else None
    return harnesses.config_root(detector, held) / relative


def drain(
    facts: Mapping[str, JsonValue],
    *,
    operations: ProviderOperations | None = None,
    patcher: RegionPatcher | None = None,
) -> DrainResult:
    """Advance initialize until a boundary. Never writes harness files here."""
    harness = facts.get("harness_id")
    if not isinstance(harness, str) or harness not in HARNESS_IDS:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="harness-id",
                    prompt="Which harness should receive the ai-stp instruction section?",
                    value_type="string",
                    choices=sorted(HARNESS_IDS),
                    why="Initialize writes one user-global surface.",
                    actor="human",
                ),
            )
        )
    harness_id = harness
    if harness_id == "antigravity" or global_instruction(harness_id) is None:
        digest = section_digest(wrap_section())
        return DrainResult(
            outcome=TaskInitializeOutcome(
                harness_id=harness_id,  # pyright: ignore[reportArgumentType]
                wrote=False,
                limitation=ANTIGRAVITY_LIMITATION,
                section_digest=digest,
            )
        )
    held: frozenset[protocol_v3.Operation]
    active: RegionPatcher | None
    if operations is None and patcher is None:
        hooked = provider_operations()
        if hooked:
            held = hooked
            active = patch_via_provider
        else:
            capabilities = bound_capabilities(harness_id)
            held = capabilities.operations if capabilities is not None else frozenset()
            ready = (
                capabilities is not None
                and PATCH_OPERATION in held
                and "instruction_section" in capabilities.plan_request_fields
            )
            active = patch_via_provider if ready else None
    else:
        held = operations() if operations is not None else frozenset()
        active = patcher
    if PATCH_OPERATION not in held or active is None or instruction_path(harness_id) is None:
        return DrainResult(
            questions=(
                TaskQuestion(
                    question_id="provider-too-old",
                    prompt=(
                        "The active provider does not declare "
                        f"{PATCH_OPERATION.value}. Upgrade it, then continue."
                    ),
                    value_type="string",
                    choices=[],
                    why="ai-stp is not a second writer of harness finals.",
                    actor="external",
                ),
            )
        )
    section = wrap_section(harness_id=harness_id)
    observation = active(harness_id, section)
    return DrainResult(
        outcome=TaskInitializeOutcome(
            harness_id=harness_id,  # pyright: ignore[reportArgumentType]
            wrote=observation.wrote,
            section_digest=observation.section_digest,
            surface=surface_relative(harness_id),
        )
    )
