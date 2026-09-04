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
from ai_stp_cli.local import harness_catalog
from ai_stp_cli.local.components import Rule
from ai_stp_cli.paths import redact_home
from ai_stp_contracts.authoring import (
    AUTHORING_DRAFT_MARKER,
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
DRAFT: Final[str] = AUTHORING_DRAFT_MARKER
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


def component_scaffold_files(
    name: str, descriptor: ComponentTemplateDescriptor
) -> dict[str, bytes]:
    """Compatibility wrapper for setup scaffolds embedding component trees."""
    return _scaffold_files(name, descriptor)


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
    native, entry, managed, projection, authoring_source = _native_source(name, descriptor)
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
        "managed_paths": [managed],
        "native_ids": [name],
        "entry_points": [entry],
        "runtime_requirements": [],
        "harness_variants": [descriptor.harness_variant],
        "supported_harness_versions": [],
    }
    if component_type == "skill":
        patch_input["description"] = f"{DRAFT} replace with the skill description."
    if descriptor.harness_variant != "portable":
        patch_input["harness_id"] = descriptor.harness_variant
    patch = ComponentPassportPatch.model_validate(patch_input)
    from ai_stp_cli.local.evaluation import reference_profile

    variant = descriptor.harness_variant
    projection_root = f"projections/{variant}"
    source_files = dict(authoring_source)
    if not source_files:
        source_files = dict(native)
    if variant == "portable":
        layout_help = (
            "This portable scaffold has no `projections/` directory. "
            "Edit `source/`. Discover and adopt copy `source/`."
        )
    else:
        layout_help = (
            f"Edit `source/`. Generated native bytes belong under `{projection_root}/` "
            "and are never the source of truth. Discover and adopt copy that projection."
        )
    files: dict[str, bytes] = {
        ".ai-stp-template.json": canonize(cast(JsonValue, descriptor.model_dump(mode="json"))),
        ".gitignore": GITIGNORE,
        "component-passport.json": canonize(
            cast(JsonValue, patch.model_dump(mode="json", exclude_none=True))
        ),
        "eval-profile.json": canonize(
            cast(JsonValue, reference_profile((component_type,)).model_dump(mode="json"))
        ),
        "README.md": (
            f"# {name}\n\n{DRAFT} replace this text with the component purpose.\n\n"
            f"{component_type} scaffold generated from "
            f"`{descriptor.template_version}`.\n\n"
            f"{layout_help}\n\n"
            "Before publication, replace every TODO marker, record exact source and license "
            "facts in `component-passport.json`, validate the draft, release an immutable "
            "component version, and publish that exact version.\n"
        ).encode(),
    }
    files.update({f"source/{path}": payload for path, payload in source_files.items()})
    if variant != "portable":
        files[f"{projection_root}/GENERATED.md"] = (
            b"# Generated projection\n\n"
            b"These native bytes are derived from `source/`. Do not edit them in place.\n"
        )
        files.update({f"{projection_root}/{path}": payload for path, payload in native.items()})
    return files


def _native_source(
    name: str, descriptor: ComponentTemplateDescriptor
) -> tuple[dict[str, bytes], str, str, str, dict[str, bytes]]:
    """Build one exact native artifact and the portable source that produced it."""
    from ai_stp_cli.local import composition

    component_type = descriptor.component_type
    harness = descriptor.harness_variant
    if harness == "portable":
        if component_type == "setting":
            raise _failure("a setting requires a concrete harness file")
        rule = None
    else:
        rule = composition.rule_for(component_type, harness)
        if rule is None:
            raise _failure(
                f"{component_type} cannot be projected to {harness} without losing semantics"
            )
    if component_type == "instruction":
        source = {"AGENTS.md": _draft_markdown(name, "instruction")}
        if rule is None:
            return {}, "AGENTS.md", "instructions/AGENTS.md", "native_files", source
        path = _instruction_native_path(rule, name)
        return (
            {path: source["AGENTS.md"]},
            PurePosixPath(path).name,
            path,
            rule.projection_kind,
            source,
        )
    if component_type == "skill":
        payload = _skill_markdown(name)
        source = {"SKILL.md": payload}
        if rule is None:
            return {}, "SKILL.md", f"skills/{name}", "native_files", source
        path = f"{rule.relative}/{name}/SKILL.md"
        return {path: payload}, "SKILL.md", f"{rule.relative}/{name}", rule.projection_kind, source
    if component_type in {"command", "agent"}:
        if component_type == "agent" and harness == "codex":
            leaf = f"{name}.toml"
            payload = _codex_agent_toml(name)
        else:
            leaf = f"{name}.md"
            payload = _draft_markdown(name, component_type)
        source = {leaf: payload}
        if rule is None:
            root = "commands" if component_type == "command" else "agents"
            return {}, leaf, f"{root}/{leaf}", "native_files", source
        path = rule.relative if rule.shape == "file" else f"{rule.relative}/{leaf}"
        return {path: payload}, PurePosixPath(path).name, path, rule.projection_kind, source
    if component_type == "setting":
        if rule is None:
            raise _failure("a setting requires a concrete harness file")
        leaf = PurePosixPath(rule.relative).name
        payload = _setting_payload(leaf)
        source = {leaf: payload}
        return {rule.relative: payload}, leaf, rule.relative, rule.projection_kind, source
    if component_type == "plugin" and harness in {"opencode", "pi"}:
        if descriptor.language not in {"javascript", "typescript"}:
            raise _failure(f"{harness} plugins are JavaScript or TypeScript modules")
        suffix = ".js" if descriptor.language == "javascript" else ".ts"
        entry = f"{name}{suffix}"
        native = {entry: _program(name, descriptor.language, "handle_request")}
        managed = f"{rule.relative}/{entry}" if rule is not None else f"plugins/{entry}"
        projection = rule.projection_kind if rule is not None else "native_files"
        return native, entry, managed, projection, {entry: native[entry]}
    if component_type == "plugin":
        manifest = {
            "claude-code": ".claude-plugin/plugin.json",
            "cursor": ".cursor-plugin/plugin.json",
        }.get(harness, "plugin.json")
        note = (
            f"# {name} skills\n\n"
            f"{DRAFT} add skill files this plugin ships. "
            "Marketplace registration is a separate setting, not this plugin.\n"
        ).encode()
        native = {
            manifest: canonize(cast(JsonValue, {"name": name, "version": "0.1.0"})),
            "skills/README.md": note,
        }
        managed = f"plugins/{name}" if rule is None else f"{rule.relative}/{name}"
        projection = "plugin" if rule is None else rule.projection_kind
        return native, manifest, managed, projection, dict(native)
    if component_type == "hook":
        entry = _program_entry(name, descriptor.language, prefix="hooks/handler")
        native_root = "hooks" if rule is None else rule.relative
        command_path = _hook_command_path(
            native_root,
            name,
            entry,
            rule is not None and rule.shape == "directory",
        )
        source = PortableHookSource(
            event="PreToolUse",
            order=0,
            failure="block",
            handler=PortableHookHandler(command=command_path),
        )
        manifest = "hooks.json" if rule is None or rule.shape != "file" else rule.relative
        native = {
            manifest: canonize(
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
            ),
            entry: _hook_program(descriptor.language),
        }
        managed = (
            "hooks.json"
            if rule is None
            else (rule.relative if rule.shape == "file" else f"{rule.relative}/{name}")
        )
        projection = "native_files" if rule is None else rule.projection_kind
        return (
            native,
            entry,
            managed,
            projection,
            {"hook-source.json": canonize(cast(JsonValue, source.model_dump(mode="json")))},
        )
    if component_type == "mcp":
        if rule is None:
            entry = _program_entry(name, descriptor.language)
            program = _program(name, descriptor.language, "handle_request")
            return {}, entry, "mcp.json", "native_files", {entry: program}
        if rule.shape == "file":
            payload = _mcp_file_stub(rule.relative)
            leaf = PurePosixPath(rule.relative).name
            return (
                {rule.relative: payload},
                leaf,
                rule.relative,
                rule.projection_kind,
                {leaf: payload},
            )
        entry = _program_entry(name, descriptor.language)
        program = _program(name, descriptor.language, "handle_request")
        path = f"{rule.relative}/{name}/{entry}"
        return (
            {path: program},
            entry,
            f"{rule.relative}/{name}",
            rule.projection_kind,
            {entry: program},
        )
    raise _failure("the component type is not in the closed eight-type vocabulary")


def _instruction_native_path(rule: Rule, name: str) -> str:
    if rule.shape == "file":
        return rule.relative
    suffix = ".mdc" if rule.harness_id == "cursor" else ".md"
    return f"{rule.relative}/{name}{suffix}"


def _draft_markdown(name: str, kind: str) -> bytes:
    return f"# {name}\n\n{DRAFT} replace this text with the bounded {kind} behavior.\n".encode()


def _skill_markdown(name: str) -> bytes:
    description = f"{DRAFT} replace with the skill description."
    body = f"{DRAFT} replace this text with the bounded skill behavior."
    return (
        f'---\nname: {name}\ndescription: "{description}"\n---\n\n# {name}\n\n{body}\n'
    ).encode()


def _codex_agent_toml(name: str) -> bytes:
    return (
        f"# {DRAFT} replace this draft Codex agent.\n"
        f'name = "{name}"\n'
        f'description = "{DRAFT} replace with the agent purpose."\n'
    ).encode()


def _mcp_file_stub(path: str) -> bytes:
    leaf = PurePosixPath(path).name
    if leaf.endswith((".json", ".jsonc")):
        return canonize(cast(JsonValue, {"mcpServers": {}}))
    if leaf.endswith(".toml"):
        return f"# {DRAFT} add the MCP server this component owns.\n".encode()
    if leaf.endswith(".js"):
        return _program("mcp", "javascript", "handle_request")
    raise _failure("the MCP surface has no supported deterministic syntax")


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
    del name
    stub = "STUB: replace before publication. A generated no-op is not a product."
    symbol = {
        "python": f"# {stub}\ndef {symbol}() -> int:\n    return 0\n",
        "typescript": f"// {stub}\nexport const {symbol} = (): number => 0;\n",
        "javascript": f"// {stub}\nexport const {symbol} = () => 0;\n",
        "rust": (
            f"// {stub}\nfn {symbol}() -> i32 {{ 0 }}\n\nfn main() {{ let _ = {symbol}(); }}\n"
        ),
        "go": (
            f"package main\n\n// {stub}\nfunc {symbol}() int {{ return 0 }}\n\n"
            f"func main() {{ _ = {symbol}() }}\n"
        ),
        "dart-flutter": f"// {stub}\nint {symbol}() => 0;\n",
    }[language]
    return symbol.encode()


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
        "rust": (
            "use std::io::{self, Read};\n"
            "fn main() { let mut input = String::new(); "
            "io::stdin().read_to_string(&mut input).unwrap(); "
            "if input.trim().is_empty() { std::process::exit(2); } }\n"
        ),
        "go": (
            'package main\n\nimport ("encoding/json"; "os")\n\n'
            "func main() { var event map[string]any; "
            "if json.NewDecoder(os.Stdin).Decode(&event) != nil { os.Exit(2) } }\n"
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
        ".rs": "",
        ".go": "",
        ".dart": "dart",
    }[PurePosixPath(entry).suffix]
    if not executable:
        raise _failure("this hook language has no directly executable native handler")
    return f"{executable} {target}"


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
