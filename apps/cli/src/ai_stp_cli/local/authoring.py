"""Safe deterministic component scaffolds and harness-specific rendering."""

from __future__ import annotations

import os
import re
import stat
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import harness_catalog
from ai_stp_contracts.authoring import (
    AUTHORING_LANGUAGES,
    AUTHORING_TYPE_LANGUAGE_MATRIX,
    AUTHORING_VARIANTS,
    ComponentScaffoldFile,
    ComponentScaffoldPlan,
    ComponentScaffoldResult,
    ComponentTemplateDescriptor,
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
        "{{#harness:pi,opencode,grok-build}}\nPortable harness guidance.\n{{/harness}}\n\n"
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


def _unused_destination(destination: Path) -> None:
    if destination.is_symlink() or destination.exists():
        raise _failure("the scaffold destination must not already exist")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise _failure("the scaffold destination parent must be an existing regular directory")


def _scaffold_files(name: str, descriptor: ComponentTemplateDescriptor) -> dict[str, bytes]:
    component_type = descriptor.component_type
    projection = "plugin" if component_type == "plugin" else "native_files"
    entry = _entry_path(name, descriptor)
    patch_input: dict[str, JsonValue] = {
        "name": name.replace("-", " ").title(),
        "description": f"Authoring draft for the {name} {component_type} component.",
        "tags": ["devops"],
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
        "managed_paths": [entry],
        "native_ids": [name],
        "entry_points": [entry],
        "runtime_requirements": [],
        "harness_variants": [descriptor.harness_variant],
        "supported_harness_versions": [],
    }
    if descriptor.harness_variant != "portable":
        patch_input["harness_id"] = descriptor.harness_variant
    patch = ComponentPassportPatch.model_validate(patch_input)
    from ai_stp_cli.local.evaluation import reference_profile

    files: dict[str, bytes] = {
        ".ai-stp-template.json": canonize(cast(JsonValue, descriptor.model_dump(mode="json"))),
        "authoring-template.md": scaffold(component_type, name).encode(),
        "component-passport.json": canonize(
            cast(JsonValue, patch.model_dump(mode="json", exclude_none=True))
        ),
        "eval-profile.json": canonize(
            cast(JsonValue, reference_profile((component_type,)).model_dump(mode="json"))
        ),
        "README.md": (
            f"# {name}\n\n{component_type} scaffold generated from "
            f"`{descriptor.template_version}`.\n"
        ).encode(),
        "SAFETY.md": (
            b"# Safety\n\nDeclare bounded filesystem, network, process, credential and "
            b"authorization needs before evaluation.\n"
        ),
        "PUBLICATION.md": (
            b"# Publication checklist\n\n- [ ] Add exact public GitHub source commit and path.\n"
            b"- [ ] Replace NOASSERTION with a reviewed redistributable license.\n"
            b"- [ ] Run passport validation and the exact SetupEvalProfile.\n"
        ),
    }
    files.update(_source_files(name, descriptor, entry))
    return files


def _entry_path(name: str, descriptor: ComponentTemplateDescriptor) -> str:
    if descriptor.language == "none":
        return {
            "skill": "SKILL.md",
            "instruction": "INSTRUCTIONS.md",
            "agent": "AGENT.md",
            "setting": "setting.json",
        }[descriptor.component_type]
    return {
        "python": f"src/{name.replace('-', '_')}/main.py",
        "typescript": "src/index.ts",
        "javascript": "src/index.js",
        "rust": "src/main.rs",
        "go": "main.go",
        "dart-flutter": f"lib/{name.replace('-', '_')}.dart",
    }[descriptor.language]


def _source_files(
    name: str, descriptor: ComponentTemplateDescriptor, entry: str
) -> dict[str, bytes]:
    if descriptor.language == "none":
        body = (
            canonize(cast(JsonValue, {"schema_version": 1, "settings": {}}))
            if descriptor.component_type == "setting"
            else (
                f"# {name}\n\nDescribe the bounded {descriptor.component_type} behavior.\n"
            ).encode()
        )
        return {
            entry: body,
            "tests/static-check.md": b"# Static check\n\nValidate the declared behavior.\n",
        }
    stem = name.replace("-", "_")
    language = descriptor.language
    symbol = {
        "mcp": "handle_request",
        "hook": "handle_event",
        "command": "run_command",
        "plugin": "activate_plugin",
    }[descriptor.component_type]
    sources: dict[str, dict[str, bytes]] = {
        "python": {
            entry: (
                f"def {symbol}() -> int:\n"
                f'    """Run the {descriptor.component_type} entry contract."""\n'
                "    return 0\n"
            ).encode(),
            f"src/{stem}/__init__.py": b"",
            "tests/test_component.py": (
                f"from {stem}.main import {symbol}\n\n\n"
                f"def test_entrypoint() -> None:\n    assert {symbol}() == 0\n"
            ).encode(),
            "pyproject.toml": (
                f'[project]\nname = "{name}"\nversion = "0.1.0"\n'
                'requires-python = ">=3.12"\n\n'
                '[tool.pytest.ini_options]\npythonpath = ["src"]\n'
            ).encode(),
        },
        "typescript": {
            entry: f"export const {symbol} = (): number => 0;\n".encode(),
            "tests/component.test.ts": (
                f"import {{ {symbol} }} from '../src/index';\n"
                f"if ({symbol}() !== 0) throw new Error('failed');\n"
            ).encode(),
            "package.json": canonize(
                cast(
                    JsonValue, {"name": name, "private": True, "version": "0.1.0", "type": "module"}
                )
            ),
        },
        "javascript": {
            entry: f"export const {symbol} = () => 0;\n".encode(),
            "tests/component.test.js": (
                f"import {{ {symbol} }} from '../src/index.js';\n"
                f"if ({symbol}() !== 0) throw new Error('failed');\n"
            ).encode(),
            "package.json": canonize(
                cast(
                    JsonValue, {"name": name, "private": True, "version": "0.1.0", "type": "module"}
                )
            ),
        },
        "rust": {
            entry: (
                f"fn {symbol}() -> i32 {{ 0 }}\n\nfn main() {{ let _ = {symbol}(); }}\n"
            ).encode(),
            "tests/smoke.rs": b"#[test]\nfn scaffold_is_loadable() { assert!(true); }\n",
            "Cargo.toml": (
                f'[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2024"\n'
            ).encode(),
        },
        "go": {
            entry: (
                f"package main\n\nfunc {symbol}() int {{ return 0 }}\n\n"
                f"func main() {{ _ = {symbol}() }}\n"
            ).encode(),
            "main_test.go": (
                b'package main\n\nimport "testing"\n\n'
                + (
                    f"func TestScaffold(t *testing.T) {{ if {symbol}() != 0 {{ t.Fail() }} }}\n"
                ).encode()
            ),
            "go.mod": f"module example.invalid/{name}\n\ngo 1.24\n".encode(),
        },
        "dart-flutter": {
            entry: f"int {symbol}() => 0;\n".encode(),
            f"test/{stem}_test.dart": (
                f"import 'package:{stem}/{stem}.dart';\n"
                f"void main() {{ assert({symbol}() == 0); }}\n"
            ).encode(),
            "pubspec.yaml": (
                f"name: {stem}\nversion: 0.1.0\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\n"
            ).encode(),
        },
    }
    return sources[language]


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
            raise _failure("the authoring template could not be opened safely")
        descriptor = os.open(path, flags)
    except OSError as error:
        raise _failure("the authoring template could not be opened safely") from error
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


def _failure(message: str) -> CliFailure:
    return CliFailure("AI_STP_VALIDATION_ERROR", message)
