"""Safe deterministic component scaffolds and harness-specific rendering."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import harness_catalog
from ai_stp_cli.paths import redact_home
from ai_stp_contracts.authoring import (
    AUTHORING_LANGUAGES,
    AUTHORING_TYPE_LANGUAGE_MATRIX,
    AUTHORING_VARIANTS,
    ComponentScaffoldFile,
    ComponentScaffoldPlan,
    ComponentScaffoldResult,
    ComponentTemplateDescriptor,
    GitInitReason,
    PortableHookHandler,
    PortableHookSource,
)
from ai_stp_contracts.component_passport import ComponentPassportPatch
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.harnesses import HARNESS_ID_ORDER

MAX_TEMPLATE_BYTES: Final[int] = 64 * 1024
TYPES: Final[frozenset[str]] = frozenset(
    {"instruction", "skill", "mcp", "hook", "command", "agent", "plugin", "setting"}
)
HARNESSES: Final[frozenset[str]] = frozenset(HARNESS_ID_ORDER)

#: Every harness that has no line of its own in the scaffold. Derived from the
#: enum rather than listed, because the listed version was written when the set
#: was five and silently stopped covering it: `cursor` and `antigravity` joined
#: `HarnessId` and rendered with no guidance line at all.
_PORTABLE_GUIDANCE: Final[str] = ",".join(
    harness for harness in HARNESS_ID_ORDER if harness not in {"claude-code", "codex"}
)
_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_OPEN = re.compile(r"^\{\{#harness:([a-z0-9,-]+)\}\}$")
_CLOSE = "{{/harness}}"
_TAG = re.compile(r"\{\{[^{}\n]+\}\}")
_PLACEHOLDERS: Final[frozenset[str]] = frozenset(
    {"harness_id", "component_name", "component_root", "config_root"}
)
LANGUAGES = AUTHORING_LANGUAGES
VARIANTS = AUTHORING_VARIANTS
TYPE_LANGUAGE_MATRIX = AUTHORING_TYPE_LANGUAGE_MATRIX
DRAFT: Final[str] = "TODO(ai-stp-scaffold):"
GITIGNORE: Final[bytes] = (
    b".DS_Store\n"
    b"Thumbs.db\n"
    b"Desktop.ini\n"
    b"__pycache__/\n"
    b"*.py[cod]\n"
    b"*.egg-info/\n"
    b".venv/\n"
    b"venv/\n"
    b"node_modules/\n"
    b".pytest_cache/\n"
    b".mypy_cache/\n"
    b".ruff_cache/\n"
    b".coverage\n"
    b"coverage.xml\n"
    b"htmlcov/\n"
    b"build/\n"
    b"dist/\n"
    b"target/\n"
    b"*.exe\n"
    b"*.pdb\n"
    b"*.db\n"
    b"*.sqlite3\n"
    b".env\n"
    b".env.*\n"
    b"!.env.example\n"
)


@dataclass(frozen=True)
class GitSideEffect:
    initialized: bool
    commit: str | None
    reason: GitInitReason | None


@dataclass(frozen=True)
class Rendered:
    content: str
    component_root: str
    placeholders: tuple[str, ...]


def scaffold(component_type: str, name: str) -> str:
    """Return a portable authoring template for any closed component type."""
    if component_type not in TYPES:
        raise _failure("the component type is not in the closed eight-type vocabulary")
    if not _NAME.fullmatch(name):
        raise _failure("the component name must be a lowercase bounded slug")
    return (
        f"# {name}\n\n"
        f"Component type: `{component_type}`.\n\n"
        "## Purpose\n\nDescribe one concrete outcome.\n\n"
        "## Native projection\n\n"
        "Target: `{{component_root}}` for `{{harness_id}}`.\n"
        "Harness configuration root: `{{config_root}}`.\n\n"
        "{{#harness:claude-code}}\nClaude Code-specific guidance.\n{{/harness}}\n"
        "{{#harness:codex}}\nCodex-specific guidance.\n{{/harness}}\n"
        f"{{{{#harness:{_PORTABLE_GUIDANCE}}}}}\nPortable harness guidance.\n{{{{/harness}}}}\n\n"
        "## Validation\n\nState the deterministic checks for this component.\n"
    )


def scaffold_plan(
    *,
    component_type: str,
    name: str,
    language: str,
    harness_variant: str,
    output: Path,
    framework: str = "none",
) -> tuple[ComponentScaffoldPlan, dict[str, bytes]]:
    """Preview every byte of one complete authoring scaffold."""
    if component_type not in TYPES or not _NAME.fullmatch(name):
        raise _failure("the component type or lowercase bounded name is invalid")
    if language not in LANGUAGES or harness_variant not in VARIANTS:
        raise _failure("the scaffold language or harness variant is unsupported")
    allowed_languages = TYPE_LANGUAGE_MATRIX[component_type]  # pyright: ignore[reportArgumentType]
    if language not in allowed_languages:
        raise _failure(
            "declarative components require language=none; executable components require a language"
        )
    declarative = language == "none"
    destination = output.expanduser().resolve(strict=False)
    _unused_destination(destination)
    descriptor = ComponentTemplateDescriptor(
        component_type=component_type,  # pyright: ignore[reportArgumentType]
        language=language,  # pyright: ignore[reportArgumentType]
        harness_variant=harness_variant,  # pyright: ignore[reportArgumentType]
        executable=not declarative,
        framework=framework,  # pyright: ignore[reportArgumentType]
    )
    files = _scaffold_files(name, descriptor)
    entries = [
        ComponentScaffoldFile(
            path=path,
            digest=digest_bytes("ai-stp:artifact:v1", payload),
            byte_length=len(payload),
        )
        for path, payload in sorted(files.items())
    ]
    body: dict[str, JsonValue] = {
        "schema_version": 1,
        "output": str(destination),
        "component_name": name,
        "descriptor": cast(JsonValue, descriptor.model_dump(mode="json")),
        "files": cast(JsonValue, [item.model_dump(mode="json") for item in entries]),
        "publication_ready": False,
        "requires_exact_source_before_publication": True,
    }
    digest = digest_bytes("ai-stp:scaffold-plan:v1", canonize(body))
    plan = ComponentScaffoldPlan.model_validate(
        {
            "plan_id": f"scaffold_plan_{digest.removeprefix('sha256:')[:24]}",
            "plan_digest": digest,
            **body,
        }
    )
    return plan, files


def apply_scaffold(
    plan: ComponentScaffoldPlan,
    files: dict[str, bytes],
    *,
    expected_digest: str,
) -> ComponentScaffoldResult:
    """Create exactly the planned new directory without replacing any path."""
    if plan.plan_digest != expected_digest:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED", "the scaffold plan digest changed before apply"
        )
    destination = Path(plan.output)
    _unused_destination(destination)
    expected_files = {item.path: (item.digest, item.byte_length, item.mode) for item in plan.files}
    observed_files = {
        path: (digest_bytes("ai-stp:artifact:v1", payload), len(payload), 0o600)
        for path, payload in files.items()
    }
    if observed_files != expected_files:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the scaffold bytes no longer match the exact plan",
        )
    directories = sorted(
        {
            parent
            for relative in files
            for parent in PurePosixPath(relative).parents
            if str(parent) != "."
        },
        key=lambda item: (len(item.parts), item.as_posix()),
    )
    created_files: list[Path] = []
    created_directories: list[Path] = []
    try:
        try:
            destination.mkdir(mode=0o700)
        except OSError as error:
            raise _failure("the scaffold destination could not be reserved safely") from error
        created_directories.append(destination)
        for relative in directories:
            directory = destination / relative.as_posix()
            directory.mkdir(mode=0o700)
            created_directories.append(directory)
        for relative, payload in files.items():
            target = destination / relative
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created_files.append(target)
            try:
                held = memoryview(payload)
                while held:
                    written = os.write(descriptor, held)
                    if written == 0:
                        raise _failure("the scaffold file could not be written completely")
                    held = held[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except BaseException:
        for target in reversed(created_files):
            with suppress(OSError):
                target.unlink()
        for directory in reversed(created_directories):
            with suppress(OSError):
                directory.rmdir()
        raise
    return ComponentScaffoldResult(
        plan_id=plan.plan_id,
        plan_digest=plan.plan_digest,
        output=str(destination),
        files_written=len(files),
    )


def component_scaffold_files(
    name: str, descriptor: ComponentTemplateDescriptor
) -> dict[str, bytes]:
    """Compatibility wrapper for setup scaffolds embedding component trees."""
    files = _scaffold_files(name, descriptor)
    if descriptor.component_type == "skill":
        projection = files.get(f"projections/{descriptor.harness_variant}/SKILL.md")
        if projection is not None:
            files["source/SKILL.md"] = projection
    return files


def write_new_tree(destination: Path, files: dict[str, bytes]) -> None:
    """Write a new tree without replacing an existing path."""
    directories = sorted(
        {
            parent
            for relative in files
            for parent in PurePosixPath(relative).parents
            if str(parent) != "."
        },
        key=lambda item: (len(item.parts), item.as_posix()),
    )
    created_files: list[Path] = []
    created_directories: list[Path] = []
    try:
        destination.mkdir(mode=0o700)
        created_directories.append(destination)
        for relative in directories:
            directory = destination / relative.as_posix()
            directory.mkdir(mode=0o700)
            created_directories.append(directory)
        for relative, payload in files.items():
            target = destination / relative
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created_files.append(target)
            try:
                os.write(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except BaseException:
        for target in reversed(created_files):
            with suppress(OSError):
                target.unlink()
        for directory in reversed(created_directories):
            with suppress(OSError):
                directory.rmdir()
        raise


def initialize_authoring_git(destination: Path) -> GitSideEffect:
    """Initialize a standalone scaffold tree when a usable Git identity exists."""
    try:
        inside = subprocess.run(
            ["git", "-C", str(destination), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return GitSideEffect(False, None, "git_unavailable")
    if inside.returncode == 0:
        return GitSideEffect(False, None, "existing_worktree")
    try:
        init = subprocess.run(
            ["git", "init"],
            cwd=destination,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if init.returncode != 0:
            return GitSideEffect(False, None, "git_unavailable")
        identity = all(
            subprocess.run(
                ["git", "config", key],
                cwd=destination,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            ).returncode
            == 0
            for key in ("user.name", "user.email")
        )
        if not identity:
            return GitSideEffect(True, None, "missing_identity")
        for command in (("git", "add", "-A"), ("git", "commit", "-m", "Initial ai-stp scaffold")):
            result = subprocess.run(
                list(command),
                cwd=destination,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                return GitSideEffect(True, None, "git_unavailable")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=destination,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        commit = head.stdout.strip()
        return (
            GitSideEffect(True, commit, None)
            if head.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", commit)
            else GitSideEffect(True, None, "git_unavailable")
        )
    except (OSError, subprocess.TimeoutExpired):
        return GitSideEffect(True, None, "git_unavailable")


def _unused_destination(destination: Path) -> None:
    if destination.is_symlink() or destination.exists():
        raise _failure("the scaffold destination must not already exist")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise _failure("the scaffold destination parent must be an existing regular directory")


def _scaffold_files(name: str, descriptor: ComponentTemplateDescriptor) -> dict[str, bytes]:
    component_type = descriptor.component_type
    native, entries, managed_paths, projection, authoring_source = _native_source(name, descriptor)
    patch_input: dict[str, JsonValue] = {
        "name": name,
        "component_type": component_type,
        "projection_kind": projection,
        "provides_capabilities": [],
        "requires_components": [],
        "requires_capabilities": [],
        "required_env": [],
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "license": {"spdx_id": "NOASSERTION", "redistribution_allowed": False},
        "conflicts": {
            "paths": [],
            "commands": [],
            "hooks": [],
            "mcp": [],
            "agents": [],
            "plugins": [],
        },
        "managed_paths": list(managed_paths),
        "native_ids": [name],
        "entry_points": list(entries),
        "runtime_requirements": (
            ["python-package:fastmcp>=2"] if descriptor.framework == "fastmcp" else []
        ),
        "harness_variants": [descriptor.harness_variant],
        "supported_harness_versions": [],
    }
    if descriptor.harness_variant != "portable":
        patch_input["harness_id"] = descriptor.harness_variant
    patch = ComponentPassportPatch.model_validate(patch_input)
    from ai_stp_cli.local.evaluation import reference_profile

    variant = descriptor.harness_variant
    projection_root = f"projections/{variant}"
    adaptation_root = f"adaptations/{variant}"
    adaptation: dict[str, JsonValue] = {
        "schema_version": 1,
        "harness_variant": variant,
        "implementation_mode": "native",
        "logical_type": component_type,
        "projection_kind": projection,
    }
    if variant != "portable":
        adaptation["harness_id"] = variant
    files: dict[str, bytes] = {
        "component.json": canonize(cast(JsonValue, descriptor.model_dump(mode="json"))),
        ".gitignore": GITIGNORE,
        "component-passport.json": canonize(
            cast(JsonValue, patch.model_dump(mode="json", exclude_none=True))
        ),
        "eval-profile.json": canonize(
            cast(JsonValue, reference_profile((component_type,)).model_dump(mode="json"))
        ),
        "README.md": (
            f"# {name}\n\n{DRAFT} replace this draft with the component's "
            "consumer-facing purpose.\n\n"
            f"This is a `{component_type}` authoring scaffold generated from "
            f"`{descriptor.template_version}`.\n\n"
            "## Source of truth\n\n"
            "Edit files under `source/`. The selected language handler is runnable "
            "with the command recorded in the source metadata.\n\n"
            + (
                f"`projections/{variant}/` is the exact native projection for `{variant}`. "
                "Regenerate it after changing source; do not edit it by hand.\n\n"
                if variant != "portable"
                else "This portable scaffold has no provider projection. Choose a concrete "
                "harness before publishing.\n\n"
            )
            + "## Before publication\n\n"
            f"- Replace every `{DRAFT}` marker with reviewed behavior and metadata.\n"
            "- Add exact public source commit/path, license, capabilities, permissions, "
            "environment names, and harness support to the passport.\n"
            "- Run the deterministic checks in `eval-profile.json` and the repository gate.\n"
        ).encode(),
        f"{adaptation_root}/adaptation.json": canonize(cast(JsonValue, adaptation)),
    }
    files.update({f"source/{path}": payload for path, payload in authoring_source.items()})
    if variant != "portable":
        files[f"{projection_root}/GENERATED.md"] = (
            b"# Generated projection\n\n"
            b"Native bytes in this directory are produced by `ai-stp/5` from `source/`.\n"
            b"Do not treat them as the source of truth.\n"
        )
        files.update({f"{projection_root}/{path}": payload for path, payload in native.items()})
    return files


def _native_source(
    name: str, descriptor: ComponentTemplateDescriptor
) -> tuple[dict[str, bytes], tuple[str, ...], tuple[str, ...], str, dict[str, bytes]]:
    """Build one exact native artifact and the portable source that produced it."""
    from ai_stp_cli.local import composition

    component_type = descriptor.component_type
    harness = descriptor.harness_variant
    rule = None if harness == "portable" else composition.rule_for(component_type, harness)
    if component_type == "setting" and harness == "portable":
        raise _failure("setting requires a concrete harness projection")
    if harness != "portable" and rule is None:
        raise _failure(
            f"{component_type} cannot be projected to {harness} without losing semantics"
        )
    if component_type == "plugin" and harness in {"opencode", "pi"}:
        if descriptor.language not in {"javascript", "typescript"}:
            raise _failure(f"{harness} plugins are JavaScript or TypeScript modules")
        suffix = ".js" if descriptor.language == "javascript" else ".ts"
        entry = f"{name}{suffix}"
        native = {entry: _program(name, descriptor.language, "activate_plugin")}
        managed = f"{rule.relative}/{entry}" if rule is not None else f"plugins/{entry}"
        projection = rule.projection_kind if rule is not None else "native_files"
        return native, (entry,), (managed,), projection, {entry: native[entry]}
    if component_type == "plugin":
        entry = _program_entry(name, descriptor.language)
        manifest = {
            "claude-code": ".claude-plugin/plugin.json",
            "cursor": ".cursor-plugin/plugin.json",
        }.get(harness, "plugin.json")
        native = {
            manifest: canonize(
                cast(
                    JsonValue,
                    {
                        "name": name,
                        "version": "0.1.0",
                        "description": f"Native {harness} plugin {name}",
                    },
                )
            ),
            entry: _program(name, descriptor.language, "activate_plugin"),
        }
        managed = f"plugins/{name}" if rule is None else f"{rule.relative}/{name}"
        projection = "plugin" if rule is None else rule.projection_kind
        return native, (entry,), (managed,), projection, {entry: native[entry]}
    if component_type == "hook":
        suffix = PurePosixPath(_program_entry(name, descriptor.language)).suffix
        parent = PurePosixPath("hooks") if rule is None else PurePosixPath(rule.relative).parent
        hook_root = (
            parent / name
            if rule is None
            else parent / "hooks" / name
            if rule.shape == "file"
            else PurePosixPath(rule.relative) / name
        )
        entry = f"{hook_root.as_posix()}/handler{suffix}"
        command_path = _command_for_file(entry, descriptor.language)
        source = PortableHookSource(
            event="PreToolUse",
            order=0,
            failure="block",
            handler=PortableHookHandler(command=command_path),
        )
        manifest_path = (
            f"{hook_root.as_posix()}/hooks.json"
            if rule is None or rule.shape == "directory"
            else rule.relative
        )
        manifest = canonize(
            {
                "hooks": {
                    source.event: [
                        {
                            "matcher": "*",
                            "hooks": [{"type": "command", "command": source.handler.command}],
                        }
                    ]
                }
            }
        )
        handler = _hook_program(descriptor.language)
        native = {manifest_path: manifest, entry: handler}
        source_files = {
            "hook-source.json": canonize(cast(JsonValue, source.model_dump(mode="json"))),
            entry: handler,
        }
        if descriptor.language == "rust":
            runner = entry.rsplit("/", 1)[0] + "/run.py"
            native[runner] = _rust_runner(entry)
            source_files[runner] = native[runner]
        managed = (
            (rule.relative,)
            if rule is not None and rule.shape == "file"
            else (hook_root.as_posix(),)
        )
        if rule is not None and rule.shape == "file":
            managed += (hook_root.as_posix(),)
        projection = "native_files" if rule is None else rule.projection_kind
        return native, (entry,), managed, projection, source_files

    if component_type in {"instruction", "command", "agent", "setting"}:
        if component_type == "instruction":
            entry = "AGENTS.md" if rule is None or rule.shape == "file" else f"{name}.md"
            payload = _instruction_source(name)
            source_files = {"AGENTS.md": payload, "CLAUDE.md": _claude_instruction_shim()}
        elif component_type == "command":
            entry = "command.md"
            payload = _text_source(name, "command")
            source_files = {entry: payload}
        elif component_type == "agent":
            entry = "agent.toml" if rule is not None and rule.relative == "agents" else "agent.md"
            payload = (
                _agent_native(name) if entry.endswith(".toml") else _text_source(name, "agent")
            )
            source_files = {"agent.md": _text_source(name, "agent")}
        else:
            entry = PurePosixPath(rule.relative).name
            payload = _setting_payload(entry)
            source_files = {"settings.json": payload}
        if rule is None:
            native = {}
            managed = (
                ("instructions" if component_type == "instruction" else "commands") + f"/{name}.md",
            )
            projection = "native_files"
        elif rule.shape == "file":
            native = {
                rule.relative: (
                    _claude_instruction_shim()
                    if component_type == "instruction" and harness == "claude-code"
                    else payload
                )
            }
            managed = (rule.relative,)
            if component_type == "instruction" and harness == "claude-code":
                native["AGENTS.md"] = payload
                managed += ("AGENTS.md",)
            projection = rule.projection_kind
        else:
            path = (
                f"{rule.relative}/{name}/{entry}"
                if component_type == "skill"
                else f"{rule.relative}/{entry}"
            )
            native = {path: payload}
            managed = (path,)
            projection = rule.projection_kind
        return native, (entry,), managed, projection, source_files

    if component_type == "skill":
        source_files = _skill_files(name)
        payload = source_files["SKILL.md"]
        if rule is None:
            return {}, ("SKILL.md",), (f"skills/{name}",), "native_files", source_files
        if rule.shape == "directory":
            native = {
                f"{rule.relative}/{name}/{path}": content for path, content in source_files.items()
            }
            return (
                native,
                ("SKILL.md",),
                (f"{rule.relative}/{name}",),
                rule.projection_kind,
                source_files,
            )
        return (
            {rule.relative: payload},
            (PurePosixPath(rule.relative).name,),
            (rule.relative,),
            rule.projection_kind,
            source_files,
        )

    if component_type == "mcp":
        suffix = PurePosixPath(_program_entry(name, descriptor.language)).suffix.removeprefix(".")
        server = f"servers/{name}/server.{suffix}"
        source_files = {server: _mcp_program(name, descriptor.language, descriptor.framework)}
        if descriptor.language == "rust":
            runner = f"servers/{name}/run.py"
            source_files[runner] = _rust_runner(server)
        if rule is None:
            return {}, (server,), (f"servers/{name}",), "native_files", source_files
        command, args = _runtime_command(server, descriptor.language, name)
        config = _mcp_config(name, rule.relative, rule.declared_key, command, args)
        native = {rule.relative: config}
        native.update(source_files)
        managed = (rule.relative, f"servers/{name}")
        return native, (server,), managed, rule.projection_kind, source_files

    raise _failure(f"unsupported component type: {component_type}")


def _text_source(name: str, component_type: str) -> bytes:
    if component_type == "command":
        return (
            f"# {name}\n\n{DRAFT} replace with the command's user-visible outcome.\n\n"
            "## Purpose\n\nState the one task this command performs.\n\n"
            "## Usage\n\nDocument the invocation, arguments, defaults, and expected output.\n\n"
            "## Behavior\n\n"
            "1. Validate arguments and refuse unsafe or ambiguous input.\n"
            "2. Perform only the documented deterministic action.\n"
            "3. Return a concise result with actionable errors.\n\n"
            "## Exit conditions\n\nDocument success, validation failure, partial failure, "
            "and recovery.\n"
        ).encode()
    if component_type == "agent":
        return (
            f"# {name}\n\n{DRAFT} replace with the bounded agent role and outcome.\n\n"
            "## Role\n\nDescribe the responsibility, scope, and explicit non-goals.\n\n"
            "## Inputs and tools\n\nList accepted inputs and the minimum "
            "tools/permissions required.\n\n"
            "## Workflow\n\n"
            "1. Inspect relevant context and identify constraints.\n"
            "2. Plan a small, reversible sequence of actions.\n"
            "3. Validate the result and report evidence.\n\n"
            "## Stop conditions\n\nStop on missing authority, unsafe input, conflicting "
            "instructions, or failed validation.\n\n"
            "## Output contract\n\nState the artifact, status, checks, and unresolved "
            "risks the agent must report.\n"
        ).encode()
    return (
        f"# {name}\n\n{DRAFT} replace this bounded {component_type} behavior "
        "with a tested contract.\n\n"
        "## Scope\n\nState what this component owns and what it deliberately does not own.\n\n"
        "## Contract\n\nDocument inputs, outputs, invariants, failure behavior, "
        "and validation commands.\n"
    ).encode()


def _instruction_source(name: str) -> bytes:
    return (
        f"# {name}\n\n{DRAFT} replace the purpose with one concrete repository outcome.\n\n"
        "## Scope and precedence\n\n"
        "These instructions apply to the repository and its nested directories.\n"
        "The user request wins; then the nearest applicable `AGENTS.md`; then this file.\n"
        "Do not invent requirements when a repository file or command can answer them.\n\n"
        "## Repository map\n\n"
        "Record the important application, package, test, documentation, and script roots.\n"
        "Keep ownership boundaries explicit so changes land in the smallest correct area.\n\n"
        "## Working loop\n\n"
        "1. Inspect the relevant code, tests, docs, and current git state.\n"
        "2. Make the smallest reversible change that satisfies the request.\n"
        "3. Add or update a focused test for changed behavior and failure paths.\n"
        "4. Run the narrow checks first, then the repository gate when practical.\n"
        "5. Review the diff for unrelated changes, secrets, generated drift, and missing docs.\n\n"
        "## Change boundaries\n\n"
        "- Preserve existing user changes and do not overwrite files without a plan.\n"
        "- Keep business rules in their owning domain/module; avoid generic dumping grounds.\n"
        "- Treat generated files as outputs: edit their source and regenerate them.\n"
        "- Do not add dependencies, network calls, credentials, or permissions without need.\n\n"
        "## Validation\n\n"
        "List the exact formatter, linter, type-checker, unit, integration, and "
        "end-to-end commands.\n"
        "State which checks are required before commit and what evidence a failure needs.\n\n"
        "## Security\n\n"
        "Never expose secrets, tokens, private data, local environment files, or untrusted input.\n"
        "Review subprocess, filesystem, network, serialization, and permission "
        "changes explicitly.\n\n"
        "## Definition of done\n\n"
        "Behavior is implemented, tests are green or failures are named, docs are current,\n"
        "generated outputs are synchronized, and the final report states files and checks.\n"
    ).encode()


def _claude_instruction_shim() -> bytes:
    return b"# Claude Code instructions\n\n@AGENTS.md\n"


def _skill_files(name: str) -> dict[str, bytes]:
    return {
        "SKILL.md": (
            f"---\nname: {name}\n"
            f"description: {DRAFT} describe what this skill does and when an agent should use it.\n"
            "compatibility: Requires only the tools and runtime documented in this skill.\n"
            "---\n\n"
            f"# {name}\n\n{DRAFT} replace this with one focused, repeatable capability.\n\n"
            "## When to use\n\n"
            "Use this skill when the request matches the bounded task described above.\n"
            "Do not activate it for unrelated work or when a safer standard workflow is enough.\n\n"
            "## Inputs and preconditions\n\n"
            "- Identify required files, arguments, permissions, and environment assumptions.\n"
            "- Validate paths, formats, size limits, and trust boundaries before acting.\n"
            "- Stop and report a missing or ambiguous precondition; do not guess.\n\n"
            "## Workflow\n\n"
            "1. Inspect the smallest relevant context and preserve unrelated changes.\n"
            "2. Follow the deterministic steps in order.\n"
            "3. Use `scripts/validate.py` as a starting point for local mechanical checks.\n"
            "4. Load `references/REFERENCE.md` only when the detailed contract is needed.\n"
            "5. Use files under `assets/` as examples, never as hidden credentials "
            "or authority.\n\n"
            "## Safety and failure handling\n\n"
            "Never disclose secrets or personal data. Avoid destructive operations "
            "without a recovery path.\n"
            "On failure, leave the workspace recoverable, include the exact check "
            "and cause, and stop.\n\n"
            "## Examples\n\n"
            "Input: a bounded task matching this skill's description.\n"
            "Output: the requested artifact plus the checks that prove it.\n\n"
            "## Done\n\n"
            "Report changed files, validation commands, observed results, and any "
            "unresolved limitation.\n"
        ).encode(),
        "references/REFERENCE.md": (
            f"# {name} reference\n\n"
            "Keep detailed, stable domain facts here so the main skill stays small.\n\n"
            "## Contract\n\n"
            "Document accepted inputs, output shape, invariants, and error semantics.\n\n"
            "## Decision table\n\n"
            "| Condition | Action | Evidence |\n"
            "|---|---|---|\n"
            "| Input is valid | Continue | Validation output |\n"
            "| Input is missing or unsafe | Stop | Named error |\n"
        ).encode(),
        "scripts/validate.py": (
            b'"""Validate the bundled example asset without external dependencies."""\n\n'
            b"import json\n"
            b"from pathlib import Path\n\n"
            b"\n"
            b"def main() -> int:\n"
            b"    asset = Path(__file__).parents[1] / 'assets' / 'example-input.json'\n"
            b"    payload = json.loads(asset.read_text(encoding='utf-8'))\n"
            b"    if not isinstance(payload, dict) or payload.get('status') != 'ok':\n"
            b"        print('example-input.json: expected an object with status=ok')\n"
            b"        return 2\n"
            b"    print('example-input.json: valid')\n"
            b"    return 0\n\n"
            b"\n"
            b"if __name__ == '__main__':\n"
            b"    raise SystemExit(main())\n"
        ),
        "assets/example-input.json": b'{\n  "status": "ok",\n  "items": ["replace-me"]\n}\n',
    }


def _agent_native(name: str) -> bytes:
    return (
        f'name = "{name}"\n'
        f'description = "{DRAFT} replace with the concise bounded agent role."\n'
        'prompt = """You are a bounded project agent.\n\n'
        "Mission: perform one documented outcome within the supplied scope.\n"
        "Before acting: inspect context, constraints, and available authority.\n"
        "During acting: make reversible changes, preserve unrelated work, and validate inputs.\n"
        "Stop on ambiguity, missing authority, unsafe input, or failed checks.\n"
        "Report changed files, evidence, failures, and remaining risks.\n"
        '"""\n'
    ).encode()


def _program_entry(name: str, language: str, *, prefix: str = "src/main") -> str:
    stem = name.replace("-", "_")
    return {
        "python": f"{prefix}.py",
        "typescript": f"{prefix}.ts",
        "javascript": f"{prefix}.js",
        "rust": f"{prefix}.rs",
        "go": f"{prefix}.go",
        "dart-flutter": f"{prefix}-{stem}.dart",
    }[language]


def _program(name: str, language: str, symbol: str) -> bytes:
    if symbol == "activate_plugin":
        return _plugin_program(name, language)
    return _mcp_program(name, language, "none")


def _plugin_program(name: str, language: str) -> bytes:
    if language in {"javascript", "typescript"}:
        return (
            f"const plugin = {{ name: {name!r}, activate(context = {{}}) {{\n"
            "  return { name: context.name || this.name, status: 'ready' };\n"
            "} };\n"
            "module.exports = plugin;\n"
        ).encode()
    if language == "python":
        return (
            f'"""Minimal plugin entry point for {name}."""\n\n'
            "def activate(context: dict | None = None) -> dict[str, str]:\n"
            f"    return {{'name': {name!r}, 'status': 'ready'}}\n"
        ).encode()
    return _text_source(name, "plugin")


def _hook_program(language: str) -> bytes:
    sources = {
        "python": (
            "import json\nimport sys\n\n"
            "def main() -> int:\n"
            "    event = json.load(sys.stdin)\n"
            "    return 0 if isinstance(event, dict) else 2\n\n"
            "if __name__ == '__main__':\n    raise SystemExit(main())\n"
        ),
        "typescript": (
            "const { readFileSync } = require('node:fs');\n"
            "const event = JSON.parse(readFileSync(0, 'utf8'));\n"
            "if (typeof event !== 'object' || event === null || "
            "Array.isArray(event)) process.exit(2);\n"
        ),
        "javascript": (
            "import { readFileSync } from 'node:fs';\n"
            "const event = JSON.parse(readFileSync(0, 'utf8'));\n"
            "if (typeof event !== 'object' || event === null || "
            "Array.isArray(event)) process.exit(2);\n"
        ),
        "rust": (
            "use std::io::{self, Read};\n"
            "fn main() { let mut input = String::new(); "
            "if io::stdin().read_to_string(&mut input).is_err() { std::process::exit(2); } "
            "let value = input.trim(); "
            "if !(value.starts_with('{') && value.ends_with('}')) { std::process::exit(2); } }\n"
        ),
        "go": (
            'package main\n\nimport (\n\t"encoding/json"\n\t"os"\n)\n\n'
            "func main() { var event map[string]any; "
            "if json.NewDecoder(os.Stdin).Decode(&event) != nil || event == nil { os.Exit(2) } }\n"
        ),
        "dart-flutter": (
            "import 'dart:convert';\nimport 'dart:io';\n"
            "void main() { final event = jsonDecode(stdin.readLineSync() ?? ''); "
            "if (event is! Map) exit(2); }\n"
        ),
    }
    return sources[language].encode()


def _command_for_file(target: str, language: str) -> str:
    executable = {
        ".py": "python",
        ".js": "node",
        ".ts": "node",
        ".rs": "python",
        ".go": "go run",
        ".dart": "dart",
    }[PurePosixPath(target).suffix]
    if language == "rust":
        return f"python {PurePosixPath(target).parent.as_posix()}/run.py"
    return f"{executable} {target}"


def _runtime_command(target: str, language: str, name: str) -> tuple[str, list[str]]:
    if language == "python":
        return "python", [target]
    if language in {"typescript", "javascript"}:
        return "node", [target]
    if language == "go":
        return "go", ["run", target]
    if language == "rust":
        return "python", [f"servers/{name}/run.py"]
    if language == "dart-flutter":
        return "dart", [target]
    raise _failure("the executable language has no runtime command")


def _rust_runner(source: str) -> bytes:
    return (
        "import os\n"
        "import subprocess\n"
        "import sys\n"
        "import tempfile\n"
        "from pathlib import Path\n\n"
        "source = Path(__file__).with_name(" + repr(PurePosixPath(source).name) + ")\n"
        "suffix = '.exe' if os.name == 'nt' else ''\n"
        "binary = Path(tempfile.gettempdir()) / ('ai-stp-' + source.stem + suffix)\n"
        "subprocess.run(['rustc', str(source), '-O', '-o', str(binary)], check=True)\n"
        "result = subprocess.run([str(binary), *sys.argv[1:]])\n"
        "raise SystemExit(result.returncode)\n"
    ).encode()


def _mcp_config(name: str, path: str, declared_key: str, command: str, args: list[str]) -> bytes:
    if path.endswith(".toml"):

        def quoted(value: str) -> str:
            return json.dumps(value, ensure_ascii=False)

        return (
            f"[{declared_key or 'mcp_servers'}.{name}]\n"
            f"command = {quoted(command)}\n"
            f"args = [{', '.join(quoted(item) for item in args)}]\n"
        ).encode()
    key = declared_key or "mcpServers"
    server = (
        {"type": "local", "command": [command, *args]}
        if key == "mcp"
        else {"command": command, "args": args}
    )
    return canonize(cast(JsonValue, {key: {name: server}}))


def _mcp_program(name: str, language: str, framework: str) -> bytes:
    if framework == "fastmcp":
        return (
            "from fastmcp import FastMCP\n\n"
            f"mcp = FastMCP(name={name!r})\n\n"
            "@mcp.tool\n"
            "def echo(text: str) -> str:\n"
            '    """Return the supplied text unchanged."""\n'
            "    return text\n\n"
            "if __name__ == '__main__':\n"
            "    mcp.run()\n"
        ).encode()
    if language == "python":
        return (
            "import json\nimport sys\n\n"
            f"SERVER_NAME = {name!r}\n"
            "def reply(request: dict) -> dict | None:\n"
            "    method = request.get('method')\n"
            "    if method == 'notifications/initialized':\n"
            "        return None\n"
            "    request_id = request.get('id')\n"
            "    if method == 'initialize':\n"
            "        result = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}, 'serverInfo': {'name': SERVER_NAME, 'version': '0.1.0'}}\n"  # noqa: E501
            "    elif method == 'tools/list':\n"
            "        result = {'tools': [{'name': 'echo', 'description': 'Return text unchanged.', 'inputSchema': {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': ['text']}}]}\n"  # noqa: E501
            "    elif method == 'tools/call':\n"
            "        result = {'content': [{'type': 'text', 'text': str(request.get('params', {}).get('arguments', {}).get('text', ''))}]}\n"  # noqa: E501
            "    else:\n"
            "        return {'jsonrpc': '2.0', 'id': request_id, 'error': {'code': -32601, 'message': 'method not found'}}\n"  # noqa: E501
            "    return {'jsonrpc': '2.0', 'id': request_id, 'result': result}\n\n"
            "for line in sys.stdin:\n"
            "    try:\n"
            "        response = reply(json.loads(line))\n"
            "        if response is not None:\n"
            "            print(json.dumps(response), flush=True)\n"
            "    except (json.JSONDecodeError, AttributeError, TypeError):\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'parse error'}}), flush=True)\n"  # noqa: E501
        ).encode()
    if language in {"typescript", "javascript"}:
        return (
            "const readline = require('node:readline');\n"
            f"const serverName = {name!r};\n"
            "const rl = readline.createInterface({ input: process.stdin });\n"
            "function reply(request) {\n"
            "  const method = request.method;\n"
            "  if (method === 'notifications/initialized') return null;\n"
            "  let result;\n"
            "  if (method === 'initialize') result = { protocolVersion: '2024-11-05', capabilities: { tools: {} }, serverInfo: { name: serverName, version: '0.1.0' } };\n"  # noqa: E501
            "  else if (method === 'tools/list') result = { tools: [{ name: 'echo', description: 'Return text unchanged.', inputSchema: { type: 'object', properties: { text: { type: 'string' } }, required: ['text'] } }] };\n"  # noqa: E501
            "  else if (method === 'tools/call') result = { content: [{ type: 'text', text: String(request.params?.arguments?.text ?? '') }] };\n"  # noqa: E501
            "  else return { jsonrpc: '2.0', id: request.id ?? null, error: { code: -32601, message: 'method not found' } };\n"  # noqa: E501
            "  return { jsonrpc: '2.0', id: request.id ?? null, result };\n"
            "}\n"
            "rl.on('line', line => { try { const response = reply(JSON.parse(line)); if (response) process.stdout.write(JSON.stringify(response) + '\\n'); } catch { process.exitCode = 2; } });\n"  # noqa: E501
        ).encode()
    if language == "go":
        return (
            'package main\n\nimport ("bufio"; "encoding/json"; "fmt"; "os")\n\n'
            f"const serverName = {json.dumps(name)}\n\n"
            'func main() { scanner := bufio.NewScanner(os.Stdin); for scanner.Scan() { var request map[string]any; if json.Unmarshal(scanner.Bytes(), &request) != nil { os.Exit(2) }; method, _ := request["method"].(string); if method == "notifications/initialized" { continue }; id := request["id"]; var result any; switch method { case "initialize": result = map[string]any{"protocolVersion": "2024-11-05", "capabilities": map[string]any{"tools": map[string]any{}}, "serverInfo": map[string]any{"name": serverName, "version": "0.1.0"}}; case "tools/list": result = map[string]any{"tools": []any{map[string]any{"name": "echo", "description": "Return text unchanged.", "inputSchema": map[string]any{"type": "object", "properties": map[string]any{"text": map[string]any{"type": "string"}}, "required": []string{"text"}}}}}; case "tools/call": result = map[string]any{"content": []any{map[string]any{"type": "text", "text": "echo"}}}; default: result = map[string]any{"error": "method not found"} }; response := map[string]any{"jsonrpc": "2.0", "id": id, "result": result}; data, _ := json.Marshal(response); fmt.Println(string(data)) } }\n'  # noqa: E501
        ).encode()
    if language == "rust":
        return (
            "use std::io::{self, BufRead};\n\n"
            f"fn main() {{ for line in io::stdin().lock().lines().flatten() {{ "
            'if line.contains("notifications/initialized") { continue; } '
            'let id = line.split("\\"id\\":").nth(1) '
            ".and_then(|v| v.split(',').next()).unwrap_or(\"null\"); "
            f'let body = if line.contains("initialize") {{ '
            f'r#"{{"protocolVersion":"2024-11-05","capabilities":{{"tools":{{}}}},'
            f'"serverInfo":{{"name":"{name}","version":"0.1.0"}}}}"#.to_string() '
            ' } else if line.contains("tools/list") { '
            'r#"{"tools":[{"name":"echo","description":"Return text unchanged."}]}"#.to_string() '
            ' } else if line.contains("tools/call") { '
            'r#"{"content":[{"type":"text","text":"echo"}]}"#.to_string() '
            ' } else { r#"{"error":{"code":-32601,"message":"method not found"}}"#.to_string() }; '
            'println!(r#"{{"jsonrpc":"2.0","id":{},"result":{}}}"#, id.trim(), body); } }\n'
        ).encode()
    if language == "dart-flutter":
        return (
            b"import 'dart:convert';\nimport 'dart:io';\n\n"
            b"void main() { stdin.transform(utf8.decoder).transform(const LineSplitter()).listen((line) { final request = jsonDecode(line) as Map<String, dynamic>; if (request['method'] == 'notifications/initialized') return; stdout.writeln(jsonEncode({'jsonrpc': '2.0', 'id': request['id'], 'result': {'content': [{'type': 'text', 'text': 'echo'}]}})); }); }\n"  # noqa: E501
        )
    raise _failure("the executable language has no MCP runtime template")


def _setting_payload(name: str) -> bytes:
    if name.endswith((".json", ".jsonc")):
        return canonize(cast(JsonValue, {}))
    if name.endswith(".toml"):
        return b"# Add the exact owned settings for this component.\n"
    raise _failure("the setting surface has no supported deterministic syntax")


def render(source: str, *, harness_id: str, component_name: str, component_root: str) -> Rendered:
    """Render strict blocks and allowlisted path placeholders outside fences."""
    if len(source.encode("utf-8")) > MAX_TEMPLATE_BYTES:
        raise _failure("the authoring template exceeds 64 KiB")
    if harness_id not in HARNESSES:
        raise _failure("the template target is not a supported concrete harness")
    if not _NAME.fullmatch(component_name):
        raise _failure("the component name must be a lowercase bounded slug")
    root = _relative_path(component_root)
    definition = harness_catalog.BY_ID[harness_id]
    values = {
        "harness_id": harness_id,
        "component_name": component_name,
        "component_root": root,
        "config_root": definition.config_root or "",
    }
    output: list[str] = []
    active: bool | None = None
    fence: str | None = None
    used: set[str] = set()
    for line in source.splitlines(keepends=True):
        stripped = line.strip()
        marker = stripped[:3]
        if fence is None and marker in {"```", "~~~"}:
            fence = marker
            if active is not False:
                output.append(line)
            continue
        if fence is not None:
            if active is not False:
                output.append(line)
            if marker == fence:
                fence = None
            continue
        opened = _OPEN.fullmatch(stripped)
        if opened:
            if active is not None:
                raise _failure("nested harness conditional blocks are forbidden")
            names = opened[1].split(",")
            if len(names) != len(set(names)) or any(name not in HARNESSES for name in names):
                raise _failure("a harness conditional names an unknown or duplicate harness")
            active = harness_id in names
            continue
        if stripped == _CLOSE:
            if active is None:
                raise _failure("a harness conditional closes without an opener")
            active = None
            continue
        if active is False:
            continue

        def substitute(match: re.Match[str]) -> str:
            tag = match.group(0)[2:-2]
            if tag not in _PLACEHOLDERS:
                raise _failure("the template contains an unknown authoring tag")
            used.add(tag)
            return values[tag]

        output.append(_TAG.sub(substitute, line))
    if fence is not None:
        raise _failure("the template contains an unclosed fenced code block")
    if active is not None:
        raise _failure("the template contains an unclosed harness conditional")
    return Rendered("".join(output), root, tuple(sorted(used)))


def read_template(path: Path) -> str:
    """Read one owner-selected regular file without links or size races."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        link_state = path.lstat()
        if stat.S_ISLNK(link_state.st_mode):
            # The sentence stays static; the subject and the cause travel in
            # details. Measured without them: a mistyped --template path
            # answered only "could not be opened safely", naming neither the
            # file it meant nor that the file simply was not there.
            raise _failure(
                "the authoring template could not be opened safely",
                template=redact_home(path),
                reason="symlink",
            )
        descriptor = os.open(path, flags)
    except OSError as error:
        raise _failure(
            "the authoring template could not be opened safely",
            template=redact_home(path),
            reason=type(error).__name__,
        ) from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size > MAX_TEMPLATE_BYTES
            or link_state.st_dev != before.st_dev
            or link_state.st_ino != before.st_ino
        ):
            raise _failure("the authoring template must be one regular file of at most 64 KiB")
        chunks: list[bytes] = []
        remaining = MAX_TEMPLATE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(payload) > MAX_TEMPLATE_BYTES
            or before.st_ino != after.st_ino
            or len(payload) != after.st_size
        ):
            raise _failure("the authoring template changed while it was read")
        try:
            return payload.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError as error:
            raise _failure("the authoring template must be UTF-8 text") from error
    finally:
        os.close(descriptor)


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or len(value) > 512
        or value.startswith(("/", "~"))
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(ord(char) < 32 for char in value)
    ):
        raise _failure("component_root must be a bounded relative POSIX path")
    return path.as_posix()


def _failure(message: str, **details: str) -> CliFailure:
    return CliFailure("AI_STP_VALIDATION_ERROR", message, details=dict(details))
