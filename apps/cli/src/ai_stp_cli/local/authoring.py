"""Safe deterministic component scaffolds and harness-specific rendering."""

from __future__ import annotations

import os
import re
import stat
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import composition, harness_catalog
from ai_stp_cli.local.components import Rule
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
SKILL_DESCRIPTION: Final[str] = (
    f"{DRAFT} replace with a third-person sentence that says when this skill is used."
)
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
    b".env\n"
    b".env.*\n"
    b"!.env.example\n"
)
_GIT_TIMEOUT: Final[int] = 30
_COMMIT_MESSAGE: Final[str] = "Initial ai-stp scaffold"


@dataclass(frozen=True)
class Rendered:
    content: str
    component_root: str
    placeholders: tuple[str, ...]


@dataclass(frozen=True)
class GitSideEffect:
    initialized: bool
    commit: str | None
    reason: GitInitReason | None


@dataclass(frozen=True)
class KindTree:
    source: dict[str, bytes]
    projections: dict[str, bytes]
    entry: str
    managed: str
    projection_kind: str
    description: str | None = None


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
    )
    files = component_scaffold_files(name, descriptor)
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
    write_new_tree(destination, files)
    git = initialize_authoring_git(destination)
    return ComponentScaffoldResult(
        plan_id=plan.plan_id,
        plan_digest=plan.plan_digest,
        output=str(destination),
        files_written=len(files),
        git_initialized=git.initialized,
        git_commit=git.commit,
        git_reason=git.reason,
    )


def write_new_tree(destination: Path, files: dict[str, bytes]) -> None:
    """Create exactly these files in a new directory, rolling back on failure."""
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


def initialize_authoring_git(destination: Path) -> GitSideEffect:
    """Init and optionally commit after a successful write. Never part of the plan."""
    if _inside_worktree(destination):
        return GitSideEffect(False, None, "existing_worktree")
    init = _git(["init"], destination)
    if init is None or init.returncode != 0:
        return GitSideEffect(False, None, "git_unavailable")
    if not _git_identity(destination):
        return GitSideEffect(True, None, "missing_identity")
    added = _git(["add", "-A"], destination)
    if added is None or added.returncode != 0:
        return GitSideEffect(True, None, "git_unavailable")
    committed = _git(["commit", "-m", _COMMIT_MESSAGE], destination)
    if committed is None or committed.returncode != 0:
        text = "" if committed is None else f"{committed.stdout}\n{committed.stderr}"
        if "user.name" in text or "user.email" in text or "who you are" in text:
            return GitSideEffect(True, None, "missing_identity")
        return GitSideEffect(True, None, "git_unavailable")
    head = _git(["rev-parse", "HEAD"], destination)
    if head is None or head.returncode != 0:
        return GitSideEffect(True, None, "git_unavailable")
    sha = head.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        return GitSideEffect(True, None, "git_unavailable")
    return GitSideEffect(True, sha, None)


def component_scaffold_files(
    name: str, descriptor: ComponentTemplateDescriptor
) -> dict[str, bytes]:
    """Return the planned regular files for one component wrapper, without git."""
    tree = _kind_tree(name, descriptor)
    patch_input: dict[str, JsonValue] = {
        "name": name,
        "component_type": descriptor.component_type,
        "projection_kind": tree.projection_kind,  # pyright: ignore[reportArgumentType]
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
        "managed_paths": [tree.managed],
        "native_ids": [name],
        "entry_points": [tree.entry],
        "runtime_requirements": [],
        "harness_variants": [descriptor.harness_variant],
        "supported_harness_versions": [],
    }
    if tree.description is not None:
        patch_input["description"] = tree.description
    if descriptor.harness_variant != "portable":
        patch_input["harness_id"] = descriptor.harness_variant
    patch = ComponentPassportPatch.model_validate(patch_input)
    from ai_stp_cli.local.evaluation import reference_profile

    files: dict[str, bytes] = {
        ".ai-stp-template.json": canonize(cast(JsonValue, descriptor.model_dump(mode="json"))),
        ".gitignore": GITIGNORE,
        "component-passport.json": canonize(
            cast(JsonValue, patch.model_dump(mode="json", exclude_none=True))
        ),
        "eval-profile.json": canonize(
            cast(JsonValue, reference_profile((descriptor.component_type,)).model_dump(mode="json"))
        ),
        "README.md": _readme(name, descriptor),
    }
    files.update({f"source/{path}": payload for path, payload in tree.source.items()})
    if descriptor.harness_variant != "portable":
        prefix = f"projections/{descriptor.harness_variant}"
        files.update({f"{prefix}/{path}": payload for path, payload in tree.projections.items()})
    return files


def _unused_destination(destination: Path) -> None:
    if destination.is_symlink() or destination.exists():
        raise _failure("the scaffold destination must not already exist")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise _failure("the scaffold destination parent must be an existing regular directory")


def _kind_tree(name: str, descriptor: ComponentTemplateDescriptor) -> KindTree:
    component_type = descriptor.component_type
    harness = descriptor.harness_variant
    language = descriptor.language
    if component_type == "setting" and harness == "portable":
        raise _failure("setting cannot be projected without a concrete harness")
    if (
        component_type == "plugin"
        and harness in {"opencode", "pi"}
        and language not in {"javascript", "typescript"}
    ):
        raise _failure(f"{harness} plugins are JavaScript or TypeScript modules")
    rule = None if harness == "portable" else composition.rule_for(component_type, harness)
    if harness != "portable" and rule is None:
        raise _failure(
            f"{component_type} cannot be projected to {harness} without losing semantics"
        )
    if component_type == "plugin":
        return _plugin_tree(name, descriptor, rule)
    if component_type == "hook":
        return _hook_tree(name, descriptor, rule)
    if component_type == "mcp":
        return _mcp_tree(name, descriptor, rule)
    if component_type == "skill":
        return _skill_tree(name, rule)
    if component_type == "instruction":
        return _instruction_tree(name, harness, rule)
    if component_type == "command":
        return _command_tree(name, rule)
    if component_type == "agent":
        return _agent_tree(name, harness, rule)
    return _setting_tree(name, harness, rule)


def _skill_tree(name: str, rule: Rule | None) -> KindTree:
    payload = _skill_markdown(name)
    return KindTree(
        source={"SKILL.md": payload},
        projections={"SKILL.md": payload},
        entry="SKILL.md",
        managed=_managed_directory("skills", name, rule),
        projection_kind=_projection_kind(rule, "native_files"),
        description=SKILL_DESCRIPTION,
    )


def _instruction_tree(name: str, harness: str, rule: Rule | None) -> KindTree:
    canon = _instruction_markdown(name)
    if harness == "claude-code":
        native_name, native = "CLAUDE.md", canon
    elif harness == "cursor":
        native_name, native = f"rules/{name}.mdc", _cursor_rule(name)
    else:
        native_name, native = "AGENTS.md", canon
    if rule is not None and rule.shape == "directory":
        managed = (
            f"{rule.relative}/{name}.mdc" if harness == "cursor" else f"{rule.relative}/{name}"
        )
    elif rule is not None:
        managed = rule.relative
    else:
        managed = "AGENTS.md"
    return KindTree(
        source={"AGENTS.md": canon},
        projections={native_name: native},
        entry="AGENTS.md" if harness != "cursor" else f"{name}.mdc",
        managed=managed,
        projection_kind=_projection_kind(rule, "native_files"),
    )


def _command_tree(name: str, rule: Rule | None) -> KindTree:
    payload = _command_markdown(name)
    entry = f"{name}.md"
    return KindTree(
        source={entry: payload},
        projections={entry: payload},
        entry=entry,
        managed=_managed_directory("commands", entry, rule),
        projection_kind=_projection_kind(rule, "native_files"),
    )


def _agent_tree(name: str, harness: str, rule: Rule | None) -> KindTree:
    if harness == "codex":
        entry = f"{name}.toml"
        payload = _agent_toml(name)
    else:
        entry = f"{name}.md"
        payload = _agent_markdown(name)
    return KindTree(
        source={entry: payload},
        projections={entry: payload},
        entry=entry,
        managed=_managed_directory("agents", entry, rule),
        projection_kind=_projection_kind(rule, "native_files"),
    )


def _plugin_tree(name: str, descriptor: ComponentTemplateDescriptor, rule: Rule | None) -> KindTree:
    harness = descriptor.harness_variant
    language = descriptor.language
    if harness in {"opencode", "pi"}:
        suffix = ".js" if language == "javascript" else ".ts"
        entry = f"{name}{suffix}"
        payload = _plugin_module(language)
        relative = rule.relative if rule is not None else "plugins"
        return KindTree(
            source={entry: payload},
            projections={entry: payload},
            entry=entry,
            managed=f"{relative}/{entry}",
            projection_kind=_projection_kind(
                rule, "plugin" if harness == "opencode" else "package"
            ),
        )
    manifest = _plugin_manifest(name)
    note = (f"{DRAFT} add nested SKILL.md packages here, or delete this file.\n").encode()
    source = {"plugin.json": manifest, "skills/README.md": note}
    native_manifest = {
        "claude-code": ".claude-plugin/plugin.json",
        "cursor": ".cursor-plugin/plugin.json",
    }.get(harness, "plugin.json")
    if rule is not None and rule.shape == "directory":
        managed = f"{rule.relative}/{name}"
        projection = rule.projection_kind or "plugin"
    else:
        managed = f"plugins/{name}"
        projection = "plugin"
    return KindTree(
        source=source,
        projections={native_manifest: manifest, "skills/README.md": note},
        entry="plugin.json",
        managed=managed,
        projection_kind=projection,
    )


def _hook_tree(name: str, descriptor: ComponentTemplateDescriptor, rule: Rule | None) -> KindTree:
    entry = _program_entry(name, descriptor.language, prefix="hooks/handler")
    native_root = "hooks" if rule is None else rule.relative
    nested = rule is not None and rule.shape == "directory"
    command_path = _hook_command_path(native_root, name, entry, nested)
    source_model = PortableHookSource(
        event="PreToolUse",
        order=0,
        failure="block",
        handler=PortableHookHandler(command=command_path),
    )
    handler = _hook_program(descriptor.language)
    inner = {
        "hooks": {
            source_model.event: [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": source_model.handler.command}],
                }
            ]
        }
    }
    if descriptor.harness_variant == "claude-code":
        projected_name, projected = "settings.json", canonize(cast(JsonValue, inner))
    elif nested:
        projected_name, projected = f"{name}.json", canonize(cast(JsonValue, inner))
    else:
        projected_name, projected = "hooks.json", canonize(cast(JsonValue, inner))
    if rule is None:
        managed = "hooks.json"
        projection = "native_files"
    elif rule.shape == "file":
        managed = rule.relative
        projection = rule.projection_kind or "native_files"
    else:
        managed = f"{rule.relative}/{name}"
        projection = rule.projection_kind or "native_files"
    return KindTree(
        source={
            "hook.json": canonize(cast(JsonValue, source_model.model_dump(mode="json"))),
            entry: handler,
        },
        projections={projected_name: projected, entry: handler},
        entry=entry,
        managed=managed,
        projection_kind=projection,
    )


def _mcp_tree(name: str, descriptor: ComponentTemplateDescriptor, rule: Rule | None) -> KindTree:
    entry = _program_entry(name, descriptor.language)
    command, args = _mcp_invocation(descriptor.language, entry)
    manifest = canonize(cast(JsonValue, {"name": name, "command": command, "args": args}))
    program = _mcp_program(descriptor.language)
    source = {"mcp.json": manifest, entry: program}
    harness = descriptor.harness_variant
    declared_key = rule.declared_key if rule is not None else ""
    if harness == "pi":
        relative = rule.relative if rule is not None else "extensions"
        projections = {entry: program}
        managed = f"{relative}/{name}"
        projection = _projection_kind(rule, "package")
    elif declared_key == "mcp_servers":
        projections = {"config.toml": _mcp_toml(name, command, args)}
        managed = rule.relative if rule is not None else "config.toml"
        projection = _projection_kind(rule, "native_files")
    elif declared_key == "mcp":
        projections = {
            "opencode.json": canonize(
                cast(JsonValue, {"mcp": {name: {"command": [command, *args]}}})
            )
        }
        managed = rule.relative if rule is not None else "opencode.json"
        projection = _projection_kind(rule, "native_files")
    elif harness == "cursor":
        projections = {
            "mcp.json": canonize(
                cast(JsonValue, {"mcpServers": {name: {"command": command, "args": args}}})
            )
        }
        managed = rule.relative if rule is not None else "mcp.json"
        projection = _projection_kind(rule, "native_files")
    elif harness == "antigravity":
        projections = {
            "mcp_config.json": canonize(
                cast(JsonValue, {"mcpServers": {name: {"command": command, "args": args}}})
            )
        }
        managed = rule.relative if rule is not None else "mcp_config.json"
        projection = _projection_kind(rule, "native_files")
    else:
        projections = {"mcp.json": manifest, entry: program}
        managed = "mcp.json"
        projection = "native_files"
    return KindTree(
        source=source,
        projections=projections,
        entry=entry,
        managed=managed,
        projection_kind=projection,
    )


def _setting_tree(name: str, harness: str, rule: Rule | None) -> KindTree:
    del name, harness
    relative = rule.relative if rule is not None else "settings.json"
    filename = PurePosixPath(relative).name
    payload = _setting_payload(filename)
    return KindTree(
        source={filename: payload},
        projections={filename: payload},
        entry=filename,
        managed=relative,
        projection_kind=_projection_kind(rule, "native_files"),
    )


def _managed_directory(default_root: str, leaf: str, rule: Rule | None) -> str:
    if rule is None:
        return f"{default_root}/{leaf}"
    if rule.shape == "file":
        return rule.relative
    return f"{rule.relative}/{leaf}"


def _projection_kind(rule: Rule | None, default: str) -> str:
    if rule is None:
        return default
    return rule.projection_kind or default


def _skill_markdown(name: str) -> bytes:
    return (
        f'---\nname: {name}\ndescription: "{SKILL_DESCRIPTION}"\n---\n\n'
        f"# {name}\n\n{DRAFT} replace this body with the skill instructions.\n"
    ).encode()


def _instruction_markdown(name: str) -> bytes:
    return (
        f"# {name}\n\n{DRAFT} replace this body with the instruction the agent should follow.\n"
    ).encode()


def _cursor_rule(name: str) -> bytes:
    del name
    return (
        f"---\ndescription: {DRAFT} one-line rule purpose\nalwaysApply: true\n---\n\n"
        f"{DRAFT} replace this body with the instruction.\n"
    ).encode()


def _command_markdown(name: str) -> bytes:
    return (
        f"---\ndescription: {DRAFT} one-line command purpose\n---\n\n"
        f"# {name}\n\n{DRAFT} replace this body with the command instructions.\n"
    ).encode()


def _agent_markdown(name: str) -> bytes:
    return (
        f"---\nname: {name}\ndescription: {DRAFT} one-line agent purpose\n---\n\n"
        f"{DRAFT} replace this body with the agent instructions.\n"
    ).encode()


def _agent_toml(name: str) -> bytes:
    return (
        f'name = "{name}"\n'
        f'description = "{DRAFT} one-line agent purpose"\n'
        'developer_instructions = """\n'
        f"{DRAFT} replace with the agent developer instructions.\n"
        '"""\n'
    ).encode()


def _plugin_manifest(name: str) -> bytes:
    return canonize(
        cast(
            JsonValue,
            {
                "name": name,
                "version": "0.1.0",
                "description": f"{DRAFT} one-line plugin purpose",
            },
        )
    )


def _plugin_module(language: str) -> bytes:
    if language == "typescript":
        return f"// {DRAFT} replace with the plugin module.\nexport default {{}};\n".encode()
    return f"// {DRAFT} replace with the plugin module.\nexport default {{}};\n".encode()


def _mcp_invocation(language: str, entry: str) -> tuple[str, list[str]]:
    runner = {
        "python": "python",
        "javascript": "node",
        "typescript": "node",
        "dart-flutter": "dart",
        "rust": "replace-me",
        "go": "replace-me",
    }[language]
    return runner, [entry]


def _mcp_toml(name: str, command: str, args: list[str]) -> bytes:
    quoted = ", ".join(f'"{item}"' for item in args)
    return (f'[mcp_servers.{name}]\ncommand = "{command}"\nargs = [{quoted}]\n').encode()


def _mcp_program(language: str) -> bytes:
    comment = f"{DRAFT} replace this file with the MCP server entry."
    sources = {
        "python": f"# {comment}\ndef handle_request() -> int:\n    return 0\n",
        "typescript": f"// {comment}\nexport const handle_request = (): number => 0;\n",
        "javascript": f"// {comment}\nexport const handle_request = () => 0;\n",
        "rust": (
            f"// {comment}\nfn handle_request() -> i32 {{ 0 }}\n"
            "fn main() { let _ = handle_request(); }\n"
        ),
        "go": (
            f"package main\n\n// {comment}\nfunc handle_request() int {{ return 0 }}\n"
            "func main() { _ = handle_request() }\n"
        ),
        "dart-flutter": f"// {comment}\nint handle_request() => 0;\n",
    }
    return sources[language].encode()


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
            "import { readFileSync } from 'node:fs';\n"
            "const event: unknown = JSON.parse(readFileSync(0, 'utf8'));\n"
            "if (typeof event !== 'object' || event === null) process.exit(2);\n"
        ),
        "javascript": (
            "import { readFileSync } from 'node:fs';\n"
            "const event = JSON.parse(readFileSync(0, 'utf8'));\n"
            "if (typeof event !== 'object' || event === null) process.exit(2);\n"
        ),
        "dart-flutter": (
            "import 'dart:convert';\nimport 'dart:io';\n"
            "void main() { final event = jsonDecode(stdin.readLineSync() ?? ''); "
            "if (event is! Map) exit(2); }\n"
        ),
    }
    return sources[language].encode()


def _hook_command_path(root: str, name: str, entry: str, nested: bool) -> str:
    target = f"{root}/{name}/{entry}" if nested else f"{PurePosixPath(root).parent}/{entry}"
    target = target.lstrip("./")
    executable = {
        ".py": "python",
        ".js": "node",
        ".ts": "node",
        ".dart": "dart",
    }[PurePosixPath(entry).suffix]
    return f"{executable} {target}"


def _setting_payload(filename: str) -> bytes:
    if filename.endswith((".json", ".jsonc")):
        return canonize(cast(JsonValue, {}))
    if filename.endswith(".toml"):
        return f"# {DRAFT} add the exact owned settings for this component.\n".encode()
    raise _failure("the setting surface has no supported deterministic syntax")


def _readme(name: str, descriptor: ComponentTemplateDescriptor) -> bytes:
    component_type = descriptor.component_type
    harness = descriptor.harness_variant
    version = descriptor.template_version
    if harness == "portable":
        layout = (
            f"- `source/` is the canonical `{component_type}` tree. Edit here.\n"
            "- Portable scaffolds have no `projections/` directory; "
            "add one when targeting a harness.\n"
        )
        adopt = "`source/`"
    else:
        layout = (
            f"- `source/` is the canonical `{component_type}` tree. Edit here.\n"
            f"- `projections/{harness}/` is the native layout for `{harness}`. "
            "It is generated; do not treat it as a second source of truth.\n"
        )
        adopt = f"`projections/{harness}/`"
    notes = _readme_notes(component_type, harness)
    return (
        f"# {name}\n\n"
        f"{DRAFT} replace this README with a consumer description of the {component_type}.\n\n"
        f"This directory is a draft `{component_type}` component (`{version}`).\n\n"
        "## Layout\n\n"
        f"{layout}"
        "- `component-passport.json` is a local draft. It is not publication-ready.\n"
        "- `eval-profile.json` is the evaluation skeleton. The scaffold does not run it.\n\n"
        f"{notes}"
        "## Replace before publication\n\n"
        f"- Every `{DRAFT}` marker.\n"
        "- License `NOASSERTION` and `redistribution_allowed: false` "
        "after a reviewed license decision.\n"
        "- An exact public GitHub commit and path in the passport.\n\n"
        "## Publication checklist\n\n"
        "- [ ] Replace draft markers with real behavior.\n"
        "- [ ] Pin exact public GitHub source commit and path.\n"
        "- [ ] Replace NOASSERTION with a reviewed redistributable license.\n"
        "- [ ] Run `component passport validate` and the exact SetupEvalProfile.\n\n"
        "## Next\n\n"
        f"`discover` / `adopt` transfer {adopt}, not the whole authoring tree. "
        "`setup compose` records a local SQLite version and is not install. "
        "Only a public provider writes harness state.\n"
    ).encode()


def _readme_notes(component_type: str, harness: str) -> str:
    notes = {
        "skill": (
            "The YAML `description` on `source/SKILL.md` is the activation contract. "
            "It must stay identical to the passport `description`.\n\n"
        ),
        "instruction": (
            "`source/AGENTS.md` is the canon. Claude Code projections use `CLAUDE.md`; "
            "Cursor uses `rules/<name>.mdc`.\n\n"
        ),
        "plugin": (
            "This package is a manifest plus optional nested skills, not an "
            "`activate_plugin` stub. Marketplace registration is a separate `setting`.\n\n"
        ),
        "hook": (
            "`source/hook.json` pins the event, order, failure policy, and handler. "
            "The native manifest is derived from it.\n\n"
        ),
        "mcp": (
            "`source/mcp.json` is the portable server identity. Some harnesses install "
            "this as a contribution to an owned settings file, not as its own surface.\n\n"
        ),
        "agent": (
            "Codex agents are TOML with `name`, `description`, and `developer_instructions`. "
            "Other harnesses use Markdown with `name` and `description`.\n\n"
        ),
        "setting": (
            "A setting is one harness-native file. Safety and permissions live in the passport.\n\n"
        ),
        "command": (
            "Keep the Markdown `description` field; harnesses use it as the command summary.\n\n"
        ),
    }
    del harness
    return notes.get(component_type, "")


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str] | None:
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            env=environment,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None


def _inside_worktree(path: Path) -> bool:
    current = path.resolve(strict=False)
    return any((candidate / ".git").exists() for candidate in (current, *current.parents))


def _git_identity(cwd: Path) -> bool:
    name = _git(["config", "--get", "user.name"], cwd)
    email = _git(["config", "--get", "user.email"], cwd)
    return (
        name is not None
        and email is not None
        and name.returncode == 0
        and email.returncode == 0
        and bool(name.stdout.strip())
        and bool(email.stdout.strip())
    )


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
